# FILE: main.py
"""UrbanSync Khon Kaen end-to-end pipeline CLI."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import uvicorn

from src import cfs_engine, complaint_processor, cv_pipeline, dashboard, spatial_join, traffic_processor


def print_banner() -> None:
    """Print the UrbanSync CLI banner."""
    print(
        "╔══════════════════════════════════════╗\n"
        "║   UrbanSync Khon Kaen Pipeline      ║\n"
        "║   BDI Hackathon 2026 · Smart City   ║\n"
        "╚══════════════════════════════════════╝"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the pipeline."""
    parser = argparse.ArgumentParser(description="Run the UrbanSync Khon Kaen data-fusion pipeline.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--complaints", default="data/complaints.xlsx")
    parser.add_argument("--traffic-csv", default="data/traffic_dashboard.csv")
    # COCO weights used universally — handles sideways, overhead, and
    # intersection cameras. VisDrone only improves pure aerial footage
    # and is not worth the complexity for a mixed dataset.
    parser.add_argument("--model", default="models/yolov8s.pt")
    parser.add_argument("--video-dir", default=None)
    parser.add_argument("--youtube-url", default=None)
    parser.add_argument("--with-nlp", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--skip-video", action="store_true")
    parser.add_argument("--max-frames", type=int, default=None, help="Max video frames to process (for sampling/speedup)")
    parser.add_argument("--save-annotated", action="store_true", default=True, help="Save annotated and seekable H.264 video")
    parser.add_argument("--no-save-annotated", action="store_false", dest="save_annotated", help="Disable saving annotated video")
    parser.add_argument("--demo-frames", action="store_true", help="Save a demo frame per video for visualization/presentations")
    parser.add_argument("--live", action="store_true", help="Show live annotated video window during processing")
    return parser.parse_args(argv)


def _ensure_required_files(complaints: Path, traffic_csv: Path) -> None:
    """Exit with a helpful message when required input data files are missing."""
    missing = [str(path) for path in [complaints, traffic_csv] if not path.exists()]
    if missing:
        print("Required input files are missing:")
        for path in missing:
            print(f"  - {path}")
        print("Place the municipal datasets under data/ or provide --complaints and --traffic-csv.")
        raise SystemExit(2)


def _timed(label: str, func, *args, **kwargs):
    """Run one pipeline step, print timing, and return the step result."""
    start = time.perf_counter()
    print(label)
    result = func(*args, **kwargs)
    print(f"Finished in {time.perf_counter() - start:.1f}s")
    return result


def run_pipeline(args: argparse.Namespace) -> dict[str, object]:
    """Run the complete UrbanSync processing pipeline and return summary data."""
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    complaints_path = Path(args.complaints)
    traffic_path = Path(args.traffic_csv)
    _ensure_required_files(complaints_path, traffic_path)
    config_dir = Path("config")
    start = time.perf_counter()

    if not args.skip_video and (args.video_dir or args.youtube_url):
        print("[Step 0/5] Video processing...")
        video_dir = Path(args.video_dir or "data/videos")
        if args.youtube_url:
            cv_pipeline.download_youtube_videos(args.youtube_url, video_dir)
        cv_pipeline.process_all_videos(video_dir, args.model, config_dir / "video_tripwires.json", max_frames=args.max_frames, save_annotated=args.save_annotated, live_display=args.live, demo_frames=args.demo_frames)

    video_counts = output_dir / "video_counts.csv"
    traffic_df = _timed(
        "[Step 1/5] Traffic data processing...",
        traffic_processor.process_traffic_data,
        traffic_path,
        video_counts if video_counts.exists() else None,
    )
    complaints_df = _timed(
        "[Step 2/5] Complaint processing...",
        complaint_processor.process_complaints,
        complaints_path,
        config_dir / "severity_lookup.json",
        config_dir / "severity_keywords.json",
        args.with_nlp,
    )
    _ = traffic_df, complaints_df
    _timed(
        "[Step 3/5] Spatial join...",
        spatial_join.run_spatial_join,
        output_dir / "complaints_enriched.csv",
        output_dir / "traffic_enriched.csv",
        config_dir / "district_bounds.json",
    )
    ranked_df = _timed("[Step 4/5] CFS computation...", cfs_engine.run_cfs_engine, output_dir / "complaints_with_traffic.csv")
    _timed(
        "[Step 5/5] Dashboard generation...",
        dashboard.build_dashboard,
        output_dir / "ranked_queue.json",
        output_dir / "traffic_enriched.csv",
        output_dir / "statistics.json",
        output_dir / "dashboard.html",
    )
    stats = json.loads((output_dir / "statistics.json").read_text(encoding="utf-8"))
    elapsed = time.perf_counter() - start
    print(f"✓ Pipeline complete in {elapsed:.1f}s")
    print(f"✓ Open complaints ranked: {len(ranked_df)}")
    print(
        f"✓ Critical: {stats.get('critical_count', 0)} | High: {stats.get('high_count', 0)} | "
        f"Medium: {stats.get('medium_count', 0)} | Low: {stats.get('low_count', 0)}"
    )
    print(f"✓ Dashboard: {output_dir / 'dashboard.html'}")
    print("→ Open dashboard in browser to view results.")
    return stats


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for pipeline execution and optional API serving."""
    print_banner()
    args = parse_args(argv)
    run_pipeline(args)
    if args.serve:
        print(f"Starting API on http://localhost:{args.port}")
        uvicorn.run("src.api:app", host="0.0.0.0", port=args.port, reload=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
