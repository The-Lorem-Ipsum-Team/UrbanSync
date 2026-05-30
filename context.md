# Context

Project context for UrbanSync Khon Kaen. Use this file to understand the product, data, pipeline, and implementation intent before generating or modifying code.

## External Context

The user provided this full-context link:

https://claude.ai/share/868e2bda-c72c-4ae9-80ff-a82397ec4e37

This environment could not directly fetch the Claude share page contents. The current project context below is derived from `prompt.txt`, `AGENTS.md`, and `progress.md`. If the Claude share contains extra decisions, paste or export that content into this repository and update this file.

## Product

UrbanSync Khon Kaen is a Smart City hackathon project for prioritizing municipal infrastructure complaints by civic impact instead of first-in-first-out order.

The system computes a Civic Friction Score (CFS) for every open complaint:

```text
CFS = complaint_severity_score * traffic_multiplier
```

The goal is to rank repair dispatch work by mobility return on investment: issues that block, slow, or endanger the most road users should move higher in the queue.

## Target Users

- Municipal operators deciding which open complaints to dispatch first.
- Hackathon judges evaluating a working data-fusion prototype.
- Technical reviewers inspecting the pipeline, API, and dashboard.

## Data Sources

### Traffic Data

`data/traffic_dashboard.csv` contains 25 traffic checkpoints in Khon Kaen.

Important fields:

- `ที่`: checkpoint number
- `เส้นทาง`: road name
- `ตำแหน่งติดตั้งเครื่องวัด`: checkpoint location description
- `Lat`: latitude
- `Lng` or `Lag`: longitude, normalized to `Lng`
- `Car`, `Motorcycle`, `Truck`: daily vehicle counts
- `รวมต่อวัน`: total vehicles per day
- `คัน/ชั่วโมง`: vehicles per hour

Optional video processing uses CCTV clips in `data/videos/*` to estimate bidirectional traffic and cross-check the dashboard counts.

### Complaint Data

`data/complaints.xlsx` contains municipal complaint records.

Important fields:

- `เลขคำร้อง`: complaint reference
- `เรื่องร้องทุกข์`: Thai free-text complaint subject
- `ประเภทคำร้อง`: complaint category
- `เขต`: district, usually `เขต 1` through `เขต 4` or `ไม่ระบุ`
- `ชุมชน`: community
- `วันที่รับเรื่อง`: received date in Buddhist Era format, `DD/MM/YYYY`
- `วันที่เสร็จ`: completion date, sometimes empty
- `สถานะ`: complaint status

Open statuses:

- `รอช่างรับเรื่อง`
- `กำลังดำเนินการ`
- `อยู่ระหว่างการติดตาม`
- `เกินกำหนด`
- `ส่งต่อหน่วยงานอื่น`

Closed status:

- `ประเมินผลเสร็จสิ้น`

## Scoring Model

Complaint severity comes from `config/severity_lookup.json`, with keyword boosts from `config/severity_keywords.json`.

Traffic multiplier is computed from daily vehicle count with a continuous linear scale:

```text
traffic_multiplier = clamp(1.0 + (รวมต่อวัน / 130,000) * 2.0, 1.0, 3.0)
```

The continuous formula replaced the original step-only multiplier thresholds so nearly equal traffic volumes do not jump across artificial priority cliffs.

Traffic tier labels are still assigned for display and filtering:

- `>130,000`: `critical`, multiplier `3.0`
- `80,000-130,000`: `high`
- `30,000-80,000`: `medium`
- `<30,000`: `low`

Complaint severity has a wider range than traffic multiplier by design. Severity is the primary dispatch signal, and traffic volume acts as a strong location multiplier and tie-breaker between similarly severe complaints.

CFS tiers:

- `>= 24`: `critical`
- `>= 15`: `high`
- `>= 8`: `medium`
- otherwise: `low`

## Required Codebase

The prompt asks for these files:

- `requirements.txt`
- `config/severity_lookup.json`
- `config/severity_keywords.json`
- `config/district_bounds.json`
- `config/video_tripwires.json`
- `src/__init__.py`
- `src/cv_pipeline.py`
- `src/traffic_processor.py`
- `src/complaint_processor.py`
- `src/spatial_join.py`
- `src/cfs_engine.py`
- `src/dashboard.py`
- `src/api.py`
- `main.py`

All files should be complete, runnable, and free of placeholders, `TODO`, and `pass` stubs.

## Pipeline

`main.py` is the only entry point.

Expected flow:

1. Optional video processing from local CCTV clips or a YouTube playlist, with `--max-frames` sampling support for long videos.
2. Traffic data loading, cleanup, tiering, and optional video cross-validation.
3. Complaint loading, Thai date parsing, open/closed classification, severity scoring, resolution baseline, and optional topic modeling.
4. Spatial join from complaint district centroids to nearest traffic checkpoint.
5. CFS computation, FIFO comparison, ranked queue generation, and statistics export.
6. Dashboard generation.
7. Optional FastAPI serving.

## Outputs

All generated outputs should go under `outputs/`.

Core outputs include:

- `outputs/traffic_enriched.csv`
- `outputs/complaints_enriched.csv`
- `outputs/resolution_baseline.json`
- `outputs/complaints_with_traffic.csv`
- `outputs/fifo_vs_cfs_comparison.csv`
- `outputs/ranked_queue.json`
- `outputs/ranked_queue.csv`
- `outputs/statistics.json`
- `outputs/dashboard.html`

Optional outputs include:

- `outputs/video_counts.csv`
- `outputs/complaint_topics.csv`

## Dashboard

The dashboard should be a complete offline-friendly HTML page with:

- dark navy background
- teal accents
- metric cards
- embedded Folium map
- traffic checkpoint layer
- open complaint layer
- top 20 priority layer
- top 20 CFS table
- pure HTML/CSS CFS tier distribution bars

Footer text from the prompt:

```text
Generated by UrbanSync · BDI Hackathon 2026 · Team Lorem Ipsum
```

## API

FastAPI endpoints expected by the prompt:

- `GET /`
- `GET /stats`
- `GET /queue`
- `GET /queue/{rank}`
- `GET /checkpoints`
- `GET /dashboard`
- `GET /stats/by-district`
- `GET /stats/by-type`

The API should load generated output files on startup and return `503` when required files are missing.

## Mock Data

`generate_mock_data.py` creates realistic local test inputs:

- `data/traffic_dashboard.csv`
- `data/complaints.xlsx`

These generated data files are intentionally ignored by git. Use them for local end-to-end verification when real municipal datasets are unavailable.

## Implementation Standards

- Python 3.10+
- Type hints on public functions
- Docstrings on all functions
- Use `pathlib.Path` instead of `os.path`
- Use UTF-8 for Thai text
- Convert Buddhist Era dates to Common Era dates for computation
- Avoid absolute paths in app code
- Print practical progress messages
- Never crash the whole pipeline on a single bad row when recoverable
- Keep modules independently importable
- Do not put `if __name__ == "__main__"` blocks in `src/*`

## Repository Instructions

Agents must follow `AGENTS.md`.

Important local rules:

- Read `progress.md` before continuing project work.
- Update `progress.md` every session.
- Prefix shell commands with `rtk` when practical.
- Keep changes small and directly tied to the user request.
- Verify work before claiming completion, or state why verification was not possible.

## Current State

As of the 2026-05-30 markdown update:

- The required config files, Python modules, `requirements.txt`, and `main.py` have been generated.
- `generate_mock_data.py` exists for creating local mock municipal datasets.
- Focused tests exist under `tests/` for traffic tiering, Thai date parsing, severity scoring, spatial joining, and CFS queue output.
- The full pipeline has previously been verified end-to-end with mock data, including dashboard and API startup.
- The repository currently does not contain generated `data/` or `outputs/` files; they are ignored by git.
- Real municipal dataset verification is still pending until those files are supplied.
- Video processing verification is still pending until CCTV clips and model weights are supplied.
- The repository is now a git repository on branch `zen-branch`.

## Next Best Step

For mock-data verification, run:

```bash
python generate_mock_data.py
python main.py --skip-video
```

For real-data verification, add the municipal datasets under `data/`, then run `python main.py --skip-video`.

After pipeline verification succeeds, open `outputs/dashboard.html` and optionally start the API with:

```bash
python main.py --skip-video --serve
```
