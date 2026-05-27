# UrbanSync Khon Kaen

UrbanSync Khon Kaen is a Smart City hackathon prototype that ranks municipal infrastructure complaints by civic impact instead of first-in-first-out order.

The project combines traffic checkpoint volume with municipal complaint severity to compute a Civic Friction Score:

```text
CFS = complaint_severity_score * traffic_multiplier
```

High-scoring complaints are prioritized because they affect more road users or represent more severe infrastructure friction.

## What It Builds

The pipeline produces:

- enriched traffic checkpoint data
- enriched complaint records with severity scores
- nearest-checkpoint joins for complaints
- ranked dispatch queues by CFS
- FIFO vs CFS comparison output
- summary statistics
- an HTML dashboard
- a FastAPI demo API

## Requirements

- Python 3.10+
- Input datasets under `data/`
- Python packages from `requirements.txt`

Install dependencies:

```bash
rtk python -m pip install -r requirements.txt
```

If `rtk` is not available in your shell, use the same commands without the `rtk` prefix.

## Required Data Files

Place these files in the repository:

```text
data/complaints.xlsx
data/traffic_dashboard.csv
```

Optional video inputs:

```text
data/videos/*.mp4
```

The complaint workbook is expected to include Thai municipal fields such as `เลขคำร้อง`, `เรื่องร้องทุกข์`, `ประเภทคำร้อง`, `เขต`, `วันที่รับเรื่อง`, `วันที่เสร็จ`, and `สถานะ`.

The traffic CSV is expected to include checkpoint fields such as `ที่`, `เส้นทาง`, `ตำแหน่งติดตั้งเครื่องวัด`, `Lat`, `Lng` or `Lag`, `Car`, `Motorcycle`, `Truck`, and `รวมต่อวัน`.

## Run The Pipeline

Run the standard data pipeline without video processing:

```bash
rtk python main.py --skip-video
```

Run with optional NLP topic modeling:

```bash
rtk python main.py --skip-video --with-nlp
```

Run with local CCTV video processing:

```bash
rtk python main.py --video-dir data/videos
```

Run and then start the API:

```bash
rtk python main.py --skip-video --serve
```

By default, the API starts on:

```text
http://localhost:8000
```

## Outputs

Generated files are written under `outputs/`:

```text
outputs/traffic_enriched.csv
outputs/complaints_enriched.csv
outputs/resolution_baseline.json
outputs/complaints_with_traffic.csv
outputs/fifo_vs_cfs_comparison.csv
outputs/ranked_queue.json
outputs/ranked_queue.csv
outputs/statistics.json
outputs/dashboard.html
```

Optional outputs:

```text
outputs/video_counts.csv
outputs/complaint_topics.csv
```

Open the dashboard after a successful run:

```text
outputs/dashboard.html
```

## API Endpoints

When serving is enabled, the FastAPI app exposes:

- `GET /`
- `GET /stats`
- `GET /queue`
- `GET /queue/{rank}`
- `GET /checkpoints`
- `GET /dashboard`
- `GET /stats/by-district`
- `GET /stats/by-type`

If generated output files are missing, data endpoints return `503`.

## Configuration

Configuration lives under `config/`:

- `severity_lookup.json`: base severity by Thai complaint type
- `severity_keywords.json`: Thai keyword boosts for complaint descriptions
- `district_bounds.json`: approximate district bounding boxes for spatial joins
- `video_tripwires.json`: default tripwire lines for video counting

## Tests

Run the focused test suite:

```bash
rtk pytest -q
```

Current tests cover:

- traffic multiplier thresholds
- Buddhist Era date parsing
- severity lookup and keyword boosts
- district-to-checkpoint spatial joins
- CFS ranking and queue output shape

## Current Status

The codebase is implemented and core tests pass in the available environment.

End-to-end pipeline verification still requires the real municipal datasets. Some optional dependencies may also need installation before using all features, especially:

- `folium` for dashboard generation
- `openpyxl` for complaint XLSX ingestion
- `supervision` for video processing

## Project Structure

```text
config/                 scoring, district, and video config
src/                    pipeline, dashboard, and API modules
tests/                  focused core behavior tests
main.py                 pipeline CLI entry point
requirements.txt        Python dependencies
context.md              stable project brief
progress.md             session handoff log
prompt.txt              original implementation prompt
```
