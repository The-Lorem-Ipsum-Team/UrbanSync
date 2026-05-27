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


def load_tripwire_config(config_path: str | Path, video_id: str | None, frame_width: int, frame_height: int) -> dict[str, Any]:
    """Load tripwire JSON and convert fractional points to pixel coordinates."""
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    selected = config.get(video_id or "", config.get("default", {}))

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
) -> dict[str, Any]:
    """Process one video and return unique tripwire-crossing vehicle counts."""
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
    tripwires = load_tripwire_config(tripwire_config_path, identifier, frame_width, frame_height)
    line_a = tripwires["line_A_points"]
    line_b = tripwires["line_B_points"]
    zone_a = sv.LineZone(start=sv.Point(*line_a[0]), end=sv.Point(*line_a[1]))
    zone_b = sv.LineZone(start=sv.Point(*line_b[0]), end=sv.Point(*line_b[1]))
    model = YOLO(str(model_path))
    crossed_a: dict[int, str] = {}
    crossed_b: dict[int, str] = {}
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
            if zone_a.in_count > previous_a and int(tracker_id) not in crossed_a:
                crossed_a[int(tracker_id)] = vehicle_class
            if zone_b.in_count > previous_b and int(tracker_id) not in crossed_b:
                crossed_b[int(tracker_id)] = vehicle_class
        previous_a = zone_a.in_count
        previous_b = zone_b.in_count
    counts_a = _count_classes(crossed_a)
    counts_b = _count_classes(crossed_b)
    car_count = counts_a["Car"] + counts_b["Car"]
    motorcycle_count = counts_a["Motorcycle"] + counts_b["Motorcycle"]
    truck_count = counts_a["Truck"] + counts_b["Truck"]
    return {
        "video_id": identifier,
        "location_name": location_name,
        "direction_A_label": tripwires["direction_A_label"],
        "direction_B_label": tripwires["direction_B_label"],
        "direction_A_total": len(crossed_a),
        "direction_B_total": len(crossed_b),
        "bidirectional_total": len(crossed_a) + len(crossed_b),
        "car_count": car_count,
        "motorcycle_count": motorcycle_count,
        "truck_count": truck_count,
        "total_unique_vehicles": car_count + motorcycle_count + truck_count,
        "processed_frames": processed_frames,
        "video_duration_seconds": round(total_frames / fps, 2) if fps else 0.0,
        "source_file": str(source),
    }


def process_all_videos(
    video_dir: str | Path,
    model_path: str | Path,
    tripwire_config_path: str | Path,
    video_location_map: dict[str, str] | None = None,
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
            rows.append(process_video(file_path, model_path, tripwire_config_path, video_id=file_path.stem, location_name=location))
        except Exception as exc:
            print(f"Video failed: {file_path.name}: {exc}")
    df = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_DIR / "video_counts.csv", index=False, encoding="utf-8-sig")
    if not df.empty:
        print(df[["location_name", "bidirectional_total", "car_count", "motorcycle_count", "truck_count"]].to_string(index=False))
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
