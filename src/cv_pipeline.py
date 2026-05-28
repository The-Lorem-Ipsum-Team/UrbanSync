# FILE: src/cv_pipeline.py
"""CCTV video vehicle-counting pipeline using YOLO and tripwires."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


OUTPUT_DIR = Path("outputs")
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov"}


def _require_video_dependencies() -> tuple[Any, Any, Any]:
    """Import optional video dependencies and raise a clear error if missing."""
    try:
        import cv2
        import supervision as sv
        from ultralytics import YOLO
    except Exception as exc:
        raise RuntimeError(f"Video processing dependencies are unavailable: {exc}") from exc
    return cv2, sv, YOLO


def detect_camera_orientation(video_path: Path, model: Any, n_frames: int = 100) -> str:
    """Detect dominant vehicle movement direction from the first n_frames.

    Returns 'sideways' if vehicles move mostly horizontally (left-right),
    or 'overhead' if vehicles move mostly vertically (up-down).
    Falls back to 'sideways' if no tracks are detected.
    """
    try:
        import cv2 as _cv2
    except Exception as exc:
        raise RuntimeError(f"OpenCV unavailable: {exc}") from exc

    cap = _cv2.VideoCapture(str(video_path))
    frame_width = int(cap.get(_cv2.CAP_PROP_FRAME_WIDTH)) or 1
    frame_height = int(cap.get(_cv2.CAP_PROP_FRAME_HEIGHT)) or 1
    cap.release()

    track_positions: dict[int, list[tuple[float, float]]] = {}
    frame_count = 0

    for result in model.track(
        source=str(video_path),
        tracker="bytetrack.yaml",
        persist=True,
        stream=True,
        verbose=False,
        classes=[2, 3, 5, 7],
    ):
        if frame_count >= n_frames:
            break
        if result.boxes is None or result.boxes.id is None:
            frame_count += 1
            continue
        for box, tid in zip(result.boxes.xyxy, result.boxes.id):
            tid = int(tid)
            x_center = float((box[0] + box[2]) / 2) / frame_width
            y_center = float((box[1] + box[3]) / 2) / frame_height
            if tid not in track_positions:
                track_positions[tid] = []
            track_positions[tid].append((x_center, y_center))
        frame_count += 1

    if not track_positions:
        return "sideways"  # default fallback — vertical tripwire works for most street cams

    total_dx, total_dy, count = 0.0, 0.0, 0
    for positions in track_positions.values():
        if len(positions) < 2:
            continue
        for i in range(1, len(positions)):
            total_dx += abs(positions[i][0] - positions[i - 1][0])
            total_dy += abs(positions[i][1] - positions[i - 1][1])
            count += 1

    if count == 0:
        return "sideways"

    mean_dx = total_dx / count
    mean_dy = total_dy / count
    return "sideways" if mean_dx >= mean_dy else "overhead"


def load_tripwire_config(
    config_path: str | Path,
    video_id: str | None,
    frame_width: int,
    frame_height: int,
    orientation: str = "sideways",
) -> dict[str, Any]:
    """Load tripwire JSON and convert fractional points to pixel coordinates.

    Priority:
    1. video_id-specific entry in config JSON  (manual override)
    2. Auto-oriented default based on detected camera direction:
       - sideways  → vertical tripwire  (counts left/right traffic flow)
       - overhead  → horizontal tripwire (counts north/south traffic flow)
    """
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))

    # 1. Per-video manual override
    if video_id and video_id in config:
        selected = config[video_id]
    else:
        # 2. Auto-orient based on detected movement direction
        if orientation == "sideways":
            selected = {
                "line_A": [[0.5, 0.05], [0.5, 0.95]],
                "line_B": [[0.48, 0.05], [0.48, 0.95]],
                "direction_A_label": "rightbound",
                "direction_B_label": "leftbound",
            }
        else:  # overhead
            selected = {
                "line_A": [[0.1, 0.5], [0.9, 0.5]],
                "line_B": [[0.1, 0.55], [0.9, 0.55]],
                "direction_A_label": "northbound",
                "direction_B_label": "southbound",
            }

    def to_pixels(points: list[list[float]]) -> list[tuple[int, int]]:
        """Convert normalized x/y points to integer pixel coordinates."""
        return [(int(x * frame_width), int(y * frame_height)) for x, y in points]

    return {
        "line_A_points": to_pixels(selected["line_A"]),
        "line_B_points": to_pixels(selected["line_B"]),
        "direction_A_label": selected.get("direction_A_label", "direction_A"),
        "direction_B_label": selected.get("direction_B_label", "direction_B"),
    }


def _class_name(class_id: int) -> str | None:
    """Map COCO class IDs to UrbanSync vehicle labels."""
    return {2: "Car", 3: "Motorcycle", 5: "Truck", 7: "Truck"}.get(int(class_id))


def _count_classes(crossed: dict[int, str]) -> dict[str, int]:
    """Count class labels stored by tracker ID."""
    return {
        "Car": sum(1 for value in crossed.values() if value == "Car"),
        "Motorcycle": sum(1 for value in crossed.values() if value == "Motorcycle"),
        "Truck": sum(1 for value in crossed.values() if value == "Truck"),
    }


def process_video(
    video_path: str | Path,
    model_path: str | Path,
    tripwire_config_path: str | Path,
    video_id: str | None = None,
    location_name: str = "unknown",
    max_frames: int | None = None,
) -> dict[str, Any]:
    """Process one video and return unique tripwire-crossing vehicle counts (scaled if sampled).

    extrapolation_reliable is False when factor > 60 (sample < 1/60th of video).
    In that case, counts are relative density estimates, not absolute daily totals.
    """
    cv2, sv, YOLO = _require_video_dependencies()
    source = Path(video_path)
    identifier = video_id or source.stem
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {source}")
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()

    # Load model first so it can be reused for orientation detection + main tracking
    model = YOLO(str(model_path))

    # Auto-detect camera orientation from first 100 frames, then configure tripwires
    print(f"  Detecting camera orientation from first 100 frames...")
    orientation = detect_camera_orientation(source, model)
    tripwire_label = "vertical" if orientation == "sideways" else "horizontal"
    print(f"  Detected: {orientation} camera → using {tripwire_label} tripwire")

    tripwires = load_tripwire_config(
        tripwire_config_path, identifier, frame_width, frame_height, orientation
    )
    line_a = tripwires["line_A_points"]
    line_b = tripwires["line_B_points"]
    zone_a = sv.LineZone(start=sv.Point(*line_a[0]), end=sv.Point(*line_a[1]))
    zone_b = sv.LineZone(start=sv.Point(*line_b[0]), end=sv.Point(*line_b[1]))
    crossed_a: dict[int, str] = {}
    crossed_b: dict[int, str] = {}
    active_trackers: dict[int, dict[str, Any]] = {}
    processed_frames = 0
    previous_a = 0
    previous_b = 0
    for result in model.track(source=str(source), tracker="bytetrack.yaml", persist=True, stream=True, verbose=False):
        processed_frames += 1
        detections = sv.Detections.from_ultralytics(result)
        class_ids = getattr(detections, "class_id", None)
        tracker_ids = getattr(detections, "tracker_id", None)
        if class_ids is None or tracker_ids is None:
            continue
        mask = [(int(class_id) in {2, 3, 5, 7}) and tracker_id is not None for class_id, tracker_id in zip(class_ids, tracker_ids)]
        detections = detections[mask]
        zone_a.trigger(detections)
        zone_b.trigger(detections)
        for class_id, tracker_id in zip(detections.class_id, detections.tracker_id):
            vehicle_class = _class_name(int(class_id))
            if vehicle_class is None or tracker_id is None:
                continue
            tid = int(tracker_id)
            if tid not in active_trackers:
                active_trackers[tid] = {"class": vehicle_class, "frames": 0}
            active_trackers[tid]["frames"] += 1
            if zone_a.in_count > previous_a and int(tracker_id) not in crossed_a:
                crossed_a[int(tracker_id)] = vehicle_class
            if zone_b.in_count > previous_b and int(tracker_id) not in crossed_b:
                crossed_b[int(tracker_id)] = vehicle_class
        previous_a = zone_a.in_count
        previous_b = zone_b.in_count
        if max_frames is not None and processed_frames >= max_frames:
            break

    # Calculate scaling factor if we did not process the whole video
    extrapolation_factor = 1.0
    if max_frames is not None and total_frames > 0 and processed_frames < total_frames:
        extrapolation_factor = float(total_frames) / float(processed_frames)
        print(f"Sampling enabled for {source.name}: processed {processed_frames}/{total_frames} frames. Scaling factor: {extrapolation_factor:.2f}x")
    sample_seconds = round(processed_frames / fps, 1) if fps else 0.0

    # Fix 3: guard against unreliably high extrapolation factors
    HIGH_FACTOR_THRESHOLD = 60  # sample covers less than 1/60th of video
    extrapolation_reliable = (extrapolation_factor <= HIGH_FACTOR_THRESHOLD)
    if not extrapolation_reliable:
        print(f"  \u26a0 Extrapolation factor {extrapolation_factor:.1f}x exceeds {HIGH_FACTOR_THRESHOLD}x threshold.")
        print(f"    Sampled {sample_seconds:.0f}s from a {total_frames / fps / 60:.0f}-min video.")
        print(f"    Counts are RELATIVE density estimates only \u2014 not absolute daily totals.")
        print(f"    For absolute counts: increase --max-frames or process the full video.")

    scaling_factor = extrapolation_factor

    # Filter out brief tracks (less than 8 frames) to eliminate shadow/glitch noise
    valid_trackers = {tid: info for tid, info in active_trackers.items() if info["frames"] >= 8}
    counts_a = _count_classes(crossed_a)
    counts_b = _count_classes(crossed_b)
    car_crossings = counts_a["Car"] + counts_b["Car"]
    motorcycle_crossings = counts_a["Motorcycle"] + counts_b["Motorcycle"]
    truck_crossings = counts_a["Truck"] + counts_b["Truck"]
    total_crossings = car_crossings + motorcycle_crossings + truck_crossings

    # SELF-HEALING MODE — METRIC CHANGE
    # Tripwire geometry failed to capture crossings (horizontal road, tight intersection).
    # Fallback: count unique tracker presences >= 8 frames as a traffic density proxy.
    # Both measure road load differently. counting_method field records which was used.
    counting_method = "tripwire"
    if total_crossings == 0 and len(valid_trackers) > 0:
        counting_method = "self_heal_presence"
        print(f"  \u26a0 Self-heal activated [{identifier}]: tripwire captured 0 crossings.")
        print(f"    Switching to presence-based count (tracks visible >= 8 frames).")
        print(f"    Stationary vehicles at signals will be included \u2014 valid density proxy.")
        car_count = int(round(sum(1 for info in valid_trackers.values() if info["class"] == "Car") * scaling_factor))
        motorcycle_count = int(round(sum(1 for info in valid_trackers.values() if info["class"] == "Motorcycle") * scaling_factor))
        truck_count = int(round(sum(1 for info in valid_trackers.values() if info["class"] == "Truck") * scaling_factor))
        direction_a_total = int(round((len(valid_trackers) / 2) * scaling_factor))
        direction_b_total = int(round((len(valid_trackers) - len(valid_trackers) // 2) * scaling_factor))
    else:
        car_count = int(round(car_crossings * scaling_factor))
        motorcycle_count = int(round(motorcycle_crossings * scaling_factor))
        truck_count = int(round(truck_crossings * scaling_factor))
        direction_a_total = int(round(len(crossed_a) * scaling_factor))
        direction_b_total = int(round(len(crossed_b) * scaling_factor))
    
    return {
        "video_id": identifier,
        "location_name": location_name,
        "direction_A_label": tripwires["direction_A_label"],
        "direction_B_label": tripwires["direction_B_label"],
        "direction_A_total": direction_a_total,
        "direction_B_total": direction_b_total,
        "bidirectional_total": direction_a_total + direction_b_total,
        "car_count": car_count,
        "motorcycle_count": motorcycle_count,
        "truck_count": truck_count,
        "total_unique_vehicles": car_count + motorcycle_count + truck_count,
        "processed_frames": processed_frames,
        "video_duration_seconds": round(total_frames / fps, 2) if fps else 0.0,
        "source_file": str(source),
        "camera_orientation": orientation,
        "counting_method": counting_method,
        "extrapolation_factor": round(extrapolation_factor, 1),
        "extrapolation_reliable": extrapolation_reliable,
        "sample_seconds": sample_seconds,
    }


def process_all_videos(
    video_dir: str | Path,
    model_path: str | Path,
    tripwire_config_path: str | Path,
    video_location_map: dict[str, str] | None = None,
    max_frames: int | None = None,
) -> pd.DataFrame:
    """Process all local video files, save outputs/video_counts.csv, and return a DataFrame."""
    try:
        from tqdm import tqdm
    except Exception:
        tqdm = lambda value, **_: value
    directory = Path(video_dir)
    files = sorted(path for path in directory.iterdir() if path.suffix.lower() in VIDEO_EXTENSIONS)
    rows: list[dict[str, Any]] = []
    for file_path in tqdm(files, desc="Processing videos"):
        try:
            location = (video_location_map or {}).get(file_path.stem, file_path.stem)
            rows.append(process_video(file_path, model_path, tripwire_config_path, video_id=file_path.stem, location_name=location, max_frames=max_frames))
        except Exception as exc:
            print(f"Video failed: {file_path.name}: {exc}")
    df = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_DIR / "video_counts.csv", index=False, encoding="utf-8-sig")
    if not df.empty:
        print(df[["location_name", "bidirectional_total", "car_count", "motorcycle_count", "truck_count"]].to_string(index=False))
        tripwire_count = sum(1 for r in rows if r.get("counting_method") == "tripwire")
        selfheal_count = sum(1 for r in rows if r.get("counting_method") == "self_heal_presence")
        print(f"  Counting method: {tripwire_count} tripwire | {selfheal_count} self-heal")
        sideways_count = sum(1 for r in rows if r.get("camera_orientation") == "sideways")
        overhead_count = sum(1 for r in rows if r.get("camera_orientation") == "overhead")
        print(f"  Camera orientation: {sideways_count} sideways | {overhead_count} overhead")
    return df


def download_youtube_videos(playlist_url: str, output_dir: str | Path) -> list[Path]:
    """Download a YouTube playlist to MP4 files and return downloaded paths."""
    try:
        import yt_dlp
    except Exception as exc:
        raise RuntimeError(f"yt-dlp is unavailable: {exc}") from exc
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    options = {
        "format": "best[height<=720]",
        "outtmpl": str(destination / "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }
    before = set(destination.glob("*"))
    with yt_dlp.YoutubeDL(options) as downloader:
        downloader.download([playlist_url])
    after = set(destination.glob("*"))
    return sorted(path for path in after - before if path.is_file())
