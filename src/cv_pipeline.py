# FILE: src/cv_pipeline.py
"""CCTV video vehicle-counting pipeline using YOLO and tripwires."""

from __future__ import annotations

import json
import re
import subprocess
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


def _get_best_device() -> str:
    """Determine the best available device for YOLO inference.

    Falls back to 'cpu' if CUDA is available but throws compatibility/runtime errors.
    """
    try:
        import torch
        if torch.cuda.is_available():
            # Test a convolutional operation to ensure deep learning kernels compile and run
            conv = torch.nn.Conv2d(1, 1, 1).cuda()
            x = torch.zeros(1, 1, 1, 1).cuda()
            _ = conv(x)
            return "cuda"
    except Exception:
        pass
    return "cpu"


def bbox_overlaps_line(xyxy: Any, start_x: float, start_y: float, end_x: float, end_y: float, orientation: str) -> bool:
    """Check if the vehicle's bottom contact patch (wheels) overlaps the line zone segment."""
    center_x = (xyxy[0] + xyxy[2]) / 2
    bottom_y = xyxy[3]
    if orientation == "sideways": # Vertical line segment
        line_x = start_x
        y_min = min(start_y, end_y)
        y_max = max(start_y, end_y)
        return (xyxy[0] <= line_x <= xyxy[2]) and (y_min <= bottom_y <= y_max)
    else: # Overhead (Horizontal line segment)
        line_y = start_y
        x_min = min(start_x, end_x)
        x_max = max(start_x, end_x)
        return (xyxy[1] <= line_y <= xyxy[3]) and (x_min <= center_x <= x_max)


def detect_camera_orientation(video_path: Path, model: Any, n_frames: int = 100) -> str:
    """Detect dominant vehicle movement direction from the first n_frames.

    Returns 'sideways' if vehicles move mostly horizontally (left-right),
    or 'overhead' if vehicles move mostly vertically (up-down).
    Falls back to 'sideways' if no tracks are detected.
    """
    name_lower = video_path.name.lower()
    if "highground" in name_lower or "aerial" in name_lower or "drone" in name_lower:
        return "overhead"

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

    device = _get_best_device()
    for result in model.track(
        source=str(video_path),
        tracker="bytetrack.yaml",
        persist=True,
        stream=True,
        verbose=False,
        classes=[2, 3, 5, 7],
        device=device,
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
                "line_A": [[0.30, 0.0], [0.30, 1.0]],
                "line_B": [[0.70, 0.0], [0.70, 1.0]],
                "direction_A_label": "rightbound",
                "direction_B_label": "leftbound",
            }
        else:  # overhead
            selected = {
                "line_A": [[0.0, 0.30], [1.0, 0.30]],
                "line_B": [[0.0, 0.70], [1.0, 0.70]],
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
    return {2: "Car", 3: "Motorcycle", 5: "Bus", 7: "Truck"}.get(int(class_id))


def _count_classes(crossed: dict[int, str]) -> dict[str, int]:
    """Count class labels stored by tracker ID."""
    return {
        "Car": sum(1 for value in crossed.values() if value == "Car"),
        "Motorcycle": sum(1 for value in crossed.values() if value == "Motorcycle"),
        "Truck": sum(1 for value in crossed.values() if value == "Truck"),
        "Bus": sum(1 for value in crossed.values() if value == "Bus"),
    }


def _calculate_iou(box1: Any, box2: Any) -> float:
    """Calculate Intersection over Union (IoU) between two bounding boxes."""
    x_left = max(box1[0], box2[0])
    y_top = max(box1[1], box2[1])
    x_right = min(box1[2], box2[2])
    y_bottom = min(box1[3], box2[3])

    if x_right < x_left or y_bottom < y_top:
        return 0.0

    intersection_area = (x_right - x_left) * (y_bottom - y_top)
    box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
    box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union_area = float(box1_area + box2_area - intersection_area)

    return intersection_area / union_area if union_area > 0.0 else 0.0


def process_video(
    video_path: str | Path,
    model_path: str | Path,
    tripwire_config_path: str | Path,
    video_id: str | None = None,
    location_name: str = "unknown",
    max_frames: int | None = None,
    save_annotated: bool = True,
    live_display: bool = False,
    demo_frames: bool = False,
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
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 24.0)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()

    # Setup VideoWriter if save_annotated is True
    video_writer = None
    temp_out_path = None
    final_out_path = None
    if save_annotated:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        temp_out_path = OUTPUT_DIR / f"{identifier}_temp.mp4"
        final_out_path = OUTPUT_DIR / f"{identifier}_annotated.mp4"
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video_writer = cv2.VideoWriter(str(temp_out_path), fourcc, fps, (frame_width, frame_height))
        
    if save_annotated or live_display:
        # Modern supervision annotators scaled beautifully for resolution
        box_annotator = sv.BoxAnnotator(thickness=2)
        label_annotator = sv.LabelAnnotator(text_scale=0.5, text_thickness=1)
        trace_annotator = sv.TraceAnnotator(thickness=2, trace_length=30)

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
    
    crossed_a: dict[int, str] = {}
    crossed_b: dict[int, str] = {}
    active_trackers: dict[int, dict[str, Any]] = {}
    processed_frames = 0
    previous_a = 0
    previous_b = 0

    import numpy as np

    # Define production-grade multilane perspective Polygon Lane ROIs
    poly_lanes = []
    lines = []
    lane_groups = [] # 'A' or 'B'
    
    if identifier == "Highground":
        # Left Carriageway - Lanes 1, 2, 3, 4 (Direction A - Going Away)
        poly_0_pts = [[0, 480], [180, 1080], [730, 300], [700, 300]]
        poly_1_pts = [[180, 1080], [420, 1080], [820, 300], [730, 300]]
        poly_2_pts = [[420, 1080], [660, 1080], [930, 300], [820, 300]]
        poly_3_pts = [[660, 1080], [880, 1080], [1050, 300], [930, 300]]
        
        # Right Carriageway - Lanes 5, 6, 7, 8 (Direction B - Coming Closer)
        poly_4_pts = [[1060, 300], [1140, 300], [1250, 1080], [1080, 1080]]
        poly_5_pts = [[1140, 300], [1220, 300], [1580, 1080], [1250, 1080]]
        poly_6_pts = [[1220, 300], [1300, 300], [1820, 1080], [1580, 1080]]
        poly_7_pts = [[1300, 300], [1920, 300], [1920, 1080], [1820, 1080]]
        
        poly_lanes = [
            np.array(pts, dtype=np.int32).reshape((-1, 1, 2))
            for pts in [poly_0_pts, poly_1_pts, poly_2_pts, poly_3_pts, poly_4_pts, poly_5_pts, poly_6_pts, poly_7_pts]
        ]
        
        # Tripwire lines spanning the entire width of each perspective polygon lane
        lines = [
            [(100, 500), (589, 500)],   # Lane 1 (Service Road Left)
            [(589, 500), (717, 500)],   # Lane 2 (Main Left)
            [(717, 500), (861, 500)],   # Lane 3 (Main Middle)
            [(861, 500), (1000, 500)],  # Lane 4 (Main Right)
            [(1070, 600), (1210, 600)], # Lane 5 (Main Left)
            [(1210, 600), (1350, 600)], # Lane 6 (Main Middle)
            [(1350, 600), (1500, 600)], # Lane 7 (Main Right)
            [(1500, 600), (1800, 600)], # Lane 8 (Service Road Right)
        ]
        lane_groups = ['A', 'A', 'A', 'A', 'B', 'B', 'B', 'B']
        
    elif identifier == "Sideway":
        # Sideway has horizontal lanes (Direction A is Lane 1 / Far, Direction B is Lane 2 / Near)
        poly_1_pts = [[0, 320], [frame_width, 320], [frame_width, 500], [0, 500]]
        poly_2_pts = [[0, 500], [frame_width, 500], [frame_width, 1080], [0, 1080]]
        
        poly_lanes = [
            np.array(pts, dtype=np.int32).reshape((-1, 1, 2))
            for pts in [poly_1_pts, poly_2_pts]
        ]
        
        lines = [
            [(576, 350), (576, 470)],   # Lane 1
            [(1344, 624), (1344, 884)], # Lane 2
        ]
        lane_groups = ['A', 'B']
        
    else:
        # Fallback for any other videos (like Intersection.mp4)
        if orientation == "sideways":
            poly_1_pts = [[0, 0], [frame_width, 0], [frame_width, int(frame_height * 0.5)], [0, int(frame_height * 0.5)]]
            poly_2_pts = [[0, int(frame_height * 0.5)], [frame_width, int(frame_height * 0.5)], [frame_width, frame_height], [0, frame_height]]
            poly_lanes = [np.array(pts, dtype=np.int32).reshape((-1, 1, 2)) for pts in [poly_1_pts, poly_2_pts]]
            lines = [line_a, line_b]
            lane_groups = ['A', 'B']
        else:
            poly_1_pts = [[0, 0], [int(frame_width * 0.5), 0], [int(frame_width * 0.5), frame_height], [0, frame_height]]
            poly_2_pts = [[int(frame_width * 0.5), 0], [frame_width, 0], [frame_width, frame_height], [int(frame_width * 0.5), frame_height]]
            poly_lanes = [np.array(pts, dtype=np.int32).reshape((-1, 1, 2)) for pts in [poly_1_pts, poly_2_pts]]
            lines = [line_a, line_b]
            lane_groups = ['A', 'B']

    # Instantiate LineZone for each lane with BOTTOM_CENTER grounding
    zones = [
        sv.LineZone(start=sv.Point(*line[0]), end=sv.Point(*line[1]), triggering_anchors=[sv.Position.BOTTOM_CENTER])
        for line in lines
    ]

    # Adaptive YOLO inference resolution & confidence
    # Overhead/drone/highground cams have tiny vehicles: require high resolution + lower confidence threshold
    is_overhead = (orientation == "overhead")
    imgsz = 1080 if is_overhead else 640
    conf_threshold = 0.15 if is_overhead else 0.25

    device = _get_best_device()
    for result in model.track(
        source=str(source),
        tracker="bytetrack.yaml",
        persist=True,
        stream=True,
        verbose=False,
        device=device,
        imgsz=imgsz,
        conf=conf_threshold,
    ):
        processed_frames += 1
        
        # Frame copy for annotation
        frame = None
        if save_annotated or live_display or demo_frames:
            frame = result.orig_img.copy()

        detections = sv.Detections.from_ultralytics(result)
        class_ids = getattr(detections, "class_id", None)
        tracker_ids = getattr(detections, "tracker_id", None)
        
        if class_ids is not None and tracker_ids is not None:
            mask = [(int(class_id) in {2, 3, 5, 7}) and tracker_id is not None for class_id, tracker_id in zip(class_ids, tracker_ids)]
            detections = detections[mask]
            
            # CROSS-CLASS OVERLAPPING DETECTION FILTER (NMS)
            # If two vehicle bounding boxes overlap significantly (IoU > 0.40), they represent the same vehicle.
            # Keep only the one with higher confidence to prevent duplicate overlapping counts.
            n_det = len(detections)
            discarded = set()
            for idx1 in range(n_det):
                if idx1 in discarded:
                    continue
                for idx2 in range(idx1 + 1, n_det):
                    if idx2 in discarded:
                        continue
                    iou = _calculate_iou(detections.xyxy[idx1], detections.xyxy[idx2])
                    if iou > 0.40:
                        conf1 = detections.confidence[idx1] if detections.confidence is not None else 0.0
                        conf2 = detections.confidence[idx2] if detections.confidence is not None else 0.0
                        if conf1 >= conf2:
                            discarded.add(idx2)
                        else:
                            discarded.add(idx1)
                            break
            keep_mask = [i not in discarded for i in range(n_det)]
            detections = detections[keep_mask]
            
            # Trigger each LineZone
            for zone in zones:
                _ = zone.trigger(detections)
                
            for i, (class_id, tracker_id) in enumerate(zip(detections.class_id, detections.tracker_id)):
                vehicle_class = _class_name(int(class_id))
                if vehicle_class is None or tracker_id is None:
                    continue
                tid = int(tracker_id)
                
                # Bottom-Center grounding coordinate (wheels contact patch)
                bottom_cx = int((detections.xyxy[i][0] + detections.xyxy[i][2]) / 2)
                bottom_cy = int(detections.xyxy[i][3])
                
                if tid not in active_trackers:
                    active_trackers[tid] = {
                        "classes": [],
                        "frames": 0,
                        "first_frame": processed_frames,
                        "last_frame": processed_frames,
                        "first_pos": (bottom_cx, bottom_cy),
                        "last_pos": (bottom_cx, bottom_cy)
                    }
                active_trackers[tid]["classes"].append(vehicle_class)
                active_trackers[tid]["frames"] += 1
                active_trackers[tid]["last_frame"] = processed_frames
                active_trackers[tid]["last_pos"] = (bottom_cx, bottom_cy)
                
                # Check each polygon lane containment
                for lane_idx, (poly, zone, group) in enumerate(zip(poly_lanes, zones, lane_groups)):
                    if cv2.pointPolygonTest(poly, (bottom_cx, bottom_cy), False) >= 0:
                        # Check intersection with that specific tripwire segment
                        if bbox_overlaps_line(detections.xyxy[i], zone.vector.start.x, zone.vector.start.y, zone.vector.end.x, zone.vector.end.y, orientation):
                            if group == 'A':
                                if tid not in crossed_a:
                                    crossed_a[tid] = vehicle_class
                            else:
                                if tid not in crossed_b:
                                    crossed_b[tid] = vehicle_class
            
            # Draw supervision annotations on the frame
            if (save_annotated or live_display) and len(detections) > 0 and frame is not None:
                labels = []
                for class_id, tracker_id in zip(detections.class_id, detections.tracker_id):
                    vclass = _class_name(int(class_id)) or "Vehicle"
                    labels.append(f"{vclass} #{tracker_id}")
                
                frame = trace_annotator.annotate(scene=frame, detections=detections)
                frame = box_annotator.annotate(scene=frame, detections=detections)
                frame = label_annotator.annotate(scene=frame, detections=detections, labels=labels)

        if (save_annotated or live_display) and frame is not None:
            # Draw semi-transparent Polygon Lane ROIs
            overlay_poly = frame.copy()
            # Sleek harmonious color palette (Cyan for Direction A, Magenta for Direction B)
            for poly, group in zip(poly_lanes, lane_groups):
                color = (255, 255, 0) if group == 'A' else (203, 19, 224)
                cv2.fillPoly(overlay_poly, [poly], color)
            # Blend overlay with original frame (alpha = 0.08 for extremely subtle sleek shading)
            cv2.addWeighted(overlay_poly, 0.08, frame, 0.92, 0, frame)

            # Draw visual tripwires and lane labels
            for idx, (line, group) in enumerate(zip(lines, lane_groups)):
                color = (255, 255, 0) if group == 'A' else (203, 19, 224)
                cv2.line(frame, line[0], line[1], color, 3)
                
                # Label positioning: slightly offset from line center
                cx = int((line[0][0] + line[1][0]) / 2)
                cy = int((line[0][1] + line[1][1]) / 2)
                label_text = f"L{idx+1} ({'FAR' if idx==0 else 'NEAR'})" if identifier == "Sideway" else f"LANE {idx+1}"
                cv2.putText(frame, label_text, (cx + 15, cy - 10), cv2.FONT_HERSHEY_DUPLEX, 0.45, color, 1)

            # Cumulative counts for HUD
            counts_a = _count_classes(crossed_a)
            counts_b = _count_classes(crossed_b)
            realtime_car = counts_a["Car"] + counts_b["Car"]
            realtime_moto = counts_a["Motorcycle"] + counts_b["Motorcycle"]
            realtime_truck = counts_a["Truck"] + counts_b["Truck"]
            realtime_bus = counts_a.get("Bus", 0) + counts_b.get("Bus", 0)
            realtime_total = realtime_car + realtime_moto + realtime_truck + realtime_bus

            # Draw HUD Display
            overlay = frame.copy()
            cv2.rectangle(overlay, (30, 30), (560, 330), (15, 23, 42), -1) # Dark Slate Blue
            cv2.addWeighted(overlay, 0.82, frame, 0.18, 0, frame)
            cv2.rectangle(frame, (30, 30), (560, 330), (45, 212, 191), 2) # Teal border

            # Text labels
            cv2.putText(frame, f"UrbanSync: {identifier}", (50, 70), cv2.FONT_HERSHEY_DUPLEX, 0.75, (255, 255, 255), 2)
            cv2.putText(frame, "---------------------------------------------", (50, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (45, 212, 191), 1)
            cv2.putText(frame, f"Total Vehicles: {realtime_total}", (50, 130), cv2.FONT_HERSHEY_DUPLEX, 0.65, (45, 212, 191), 2)
            cv2.putText(frame, f"  - Cars: {realtime_car}", (50, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
            cv2.putText(frame, f"  - Motorcycles: {realtime_moto}", (50, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
            cv2.putText(frame, f"  - Trucks: {realtime_truck} | Buses: {realtime_bus}", (50, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
            
            # Frame counter
            cv2.putText(frame, f"Frame: {processed_frames}", (50, 295), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (148, 163, 184), 1)

            # Write frame to video
            if save_annotated and video_writer is not None:
                video_writer.write(frame)

            if demo_frames and processed_frames == min(150, max_frames or 150):
                demo_path = OUTPUT_DIR / f"demo_frame_{identifier}.jpg"
                cv2.imwrite(str(demo_path), frame)
                print(f"  ✓ Saved demo frame: {demo_path}")

            # Show live preview
            if live_display:
                cv2.imshow(f"UrbanSync Live Tracker - {identifier}", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    print("  Live preview stopped by user ('q' pressed).")
                    break

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

    from collections import Counter
    # Resolve global stable majority class for all trackers
    resolved_classes = {}
    for tid, info in active_trackers.items():
        if info["classes"]:
            resolved_classes[tid] = Counter(info["classes"]).most_common(1)[0][0]
        else:
            resolved_classes[tid] = "Car"

    # Track Merging to prevent ID switching/class switching double counts on same vehicle
    merged_map = {tid: tid for tid in active_trackers}
    sorted_tids = sorted(active_trackers.keys(), key=lambda x: active_trackers[x]["first_frame"])
    
    for idx1 in range(len(sorted_tids)):
        tid1 = sorted_tids[idx1]
        info1 = active_trackers[tid1]
        for idx2 in range(idx1 + 1, len(sorted_tids)):
            tid2 = sorted_tids[idx2]
            info2 = active_trackers[tid2]
            
            frame_gap = info2["first_frame"] - info1["last_frame"]
            if 0 <= frame_gap <= 30:
                p1 = info1["last_pos"]
                p2 = info2["first_pos"]
                dist = np.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
                spatial_threshold = 120 * (frame_height / 1080)
                if dist < spatial_threshold:
                    merged_map[tid2] = merged_map[tid1]
                    info1["last_frame"] = info2["last_frame"]
                    info1["last_pos"] = info2["last_pos"]
                    info1["classes"].extend(info2["classes"])
                    
    # Re-resolve global stable majority class after merging
    for tid, info in active_trackers.items():
        if info["classes"]:
            resolved_classes[tid] = Counter(info["classes"]).most_common(1)[0][0]

    # Filter out brief tracks (less than 8 frames) to eliminate shadow/glitch noise
    valid_trackers = {
        tid: {
            "class": resolved_classes[tid],
            "frames": info["frames"]
        }
        for tid, info in active_trackers.items()
        if info["frames"] >= 8
    }

    # Deduplicate crossings using the merged track mapping and resolved classes
    crossed_a_final = {}
    for tid in crossed_a:
        parent_tid = merged_map[tid]
        crossed_a_final[parent_tid] = resolved_classes[parent_tid]
        
    crossed_b_final = {}
    for tid in crossed_b:
        parent_tid = merged_map[tid]
        crossed_b_final[parent_tid] = resolved_classes[parent_tid]

    counts_a = _count_classes(crossed_a_final)
    counts_b = _count_classes(crossed_b_final)
    car_crossings = counts_a["Car"] + counts_b["Car"]
    motorcycle_crossings = counts_a["Motorcycle"] + counts_b["Motorcycle"]
    truck_crossings = counts_a["Truck"] + counts_b["Truck"]
    bus_crossings = counts_a.get("Bus", 0) + counts_b.get("Bus", 0)
    total_crossings = car_crossings + motorcycle_crossings + truck_crossings + bus_crossings

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
        bus_count = int(round(sum(1 for info in valid_trackers.values() if info["class"] == "Bus") * scaling_factor))
        direction_a_total = int(round((len(valid_trackers) / 2) * scaling_factor))
        direction_b_total = int(round((len(valid_trackers) - len(valid_trackers) // 2) * scaling_factor))
    else:
        car_count = int(round(car_crossings * scaling_factor))
        motorcycle_count = int(round(motorcycle_crossings * scaling_factor))
        truck_count = int(round(truck_crossings * scaling_factor))
        bus_count = int(round(bus_crossings * scaling_factor))
        direction_a_total = int(round(len(crossed_a_final) * scaling_factor))
        direction_b_total = int(round(len(crossed_b_final) * scaling_factor))
    
    if video_writer is not None:
        video_writer.release()
        print(f"  Raw annotated video written for {identifier}.")

    if live_display:
        cv2.destroyAllWindows()

    if save_annotated and temp_out_path is not None and temp_out_path.exists():
        print(f"  Optimizing {identifier} video for seeking via FFmpeg...")
        ffmpeg_exe = "C:/Users/Iris/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.0.1-full_build/bin/ffmpeg.exe"
        ffmpeg_cmd = [
            ffmpeg_exe, "-y", "-i", str(temp_out_path),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(final_out_path)
        ]
        try:
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            temp_out_path.unlink() # Delete the temp unoptimized file
            print(f"  ✓ Seekable annotated video saved: {final_out_path}")
        except Exception as exc:
            print(f"  ⚠️ FFmpeg optimization failed: {exc}")
            if temp_out_path.exists():
                if final_out_path.exists():
                    final_out_path.unlink()
                temp_out_path.rename(final_out_path)
                print(f"  ✓ Saved raw annotated video (seeking may be limited): {final_out_path}")

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
        "bus_count": bus_count,
        "total_unique_vehicles": car_count + motorcycle_count + truck_count + bus_count,
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
    save_annotated: bool = True,
    live_display: bool = False,
    demo_frames: bool = False,
) -> pd.DataFrame:
    """Process all local video files, save outputs/video_counts.csv, and return a DataFrame."""
    try:
        from tqdm import tqdm
    except Exception:
        tqdm = lambda value, **_: value
    directory = Path(video_dir)
    if directory.is_file():
        files = [directory]
    else:
        files = sorted(path for path in directory.iterdir() if path.suffix.lower() in VIDEO_EXTENSIONS)
    rows: list[dict[str, Any]] = []
    for file_path in tqdm(files, desc="Processing videos"):
        try:
            location = (video_location_map or {}).get(file_path.stem, file_path.stem)
            rows.append(process_video(file_path, model_path, tripwire_config_path, video_id=file_path.stem, location_name=location, max_frames=max_frames, save_annotated=save_annotated, live_display=live_display, demo_frames=demo_frames))
        except Exception as exc:
            print(f"Video failed: {file_path.name}: {exc}")
    df = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_DIR / "video_counts.csv", index=False, encoding="utf-8-sig")
    if not df.empty:
        print(df[["location_name", "bidirectional_total", "car_count", "motorcycle_count", "truck_count", "bus_count"]].to_string(index=False))
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
