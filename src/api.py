# FILE: src/api.py
"""FastAPI server for UrbanSync generated outputs."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse


OUTPUT_DIR = Path("outputs")
_queue: list[dict[str, Any]] | None = None
_stats: dict[str, Any] | None = None
_checkpoints: list[dict[str, Any]] | None = None


def _load_outputs() -> None:
    """Load queue, statistics, and checkpoint files into module globals."""
    global _queue, _stats, _checkpoints
    queue_path = OUTPUT_DIR / "ranked_queue.json"
    stats_path = OUTPUT_DIR / "statistics.json"
    traffic_path = OUTPUT_DIR / "traffic_enriched.csv"
    if not (queue_path.exists() and stats_path.exists() and traffic_path.exists()):
        _queue = None
        _stats = None
        _checkpoints = None
        return
    _queue = json.loads(queue_path.read_text(encoding="utf-8")).get("queue", [])
    _stats = json.loads(stats_path.read_text(encoding="utf-8"))
    _checkpoints = pd.read_csv(traffic_path).fillna("").to_dict(orient="records")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """FastAPI lifespan hook that loads generated output files on startup."""
    _load_outputs()
    yield


app = FastAPI(title="UrbanSync Khon Kaen API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _require_queue() -> list[dict[str, Any]]:
    """Return loaded queue data or raise a 503 error."""
    if _queue is None:
        raise HTTPException(status_code=503, detail="UrbanSync outputs are missing. Run main.py first.")
    return _queue


def _require_stats() -> dict[str, Any]:
    """Return loaded statistics data or raise a 503 error."""
    if _stats is None:
        raise HTTPException(status_code=503, detail="UrbanSync statistics are missing. Run main.py first.")
    return _stats


def _require_checkpoints() -> list[dict[str, Any]]:
    """Return loaded checkpoint data or raise a 503 error."""
    if _checkpoints is None:
        raise HTTPException(status_code=503, detail="UrbanSync checkpoint output is missing. Run main.py first.")
    return _checkpoints


@app.get("/")
def root() -> dict[str, Any]:
    """Return API status and loaded complaint count."""
    return {"status": "ok", "project": "UrbanSync Khon Kaen", "total_complaints": len(_queue) if _queue else 0}


@app.get("/stats")
def stats() -> dict[str, Any]:
    """Return summary CFS statistics."""
    return _require_stats()


@app.get("/queue")
def queue(
    limit: int = Query(50, ge=1, le=500),
    skip: int = Query(0, ge=0),
    tier: str | None = Query(None),
    district: str | None = Query(None),
) -> dict[str, Any]:
    """Return paginated ranked queue entries with optional filters."""
    rows = _require_queue()
    if tier:
        rows = [row for row in rows if row.get("cfs_tier") == tier]
    if district:
        rows = [row for row in rows if row.get("district") == district]
    page = rows[skip : skip + limit]
    return {"total": len(rows), "returned": len(page), "skip": skip, "limit": limit, "queue": page}


@app.get("/queue/{rank}")
def queue_by_rank(rank: int) -> dict[str, Any]:
    """Return one queue record by priority rank."""
    for row in _require_queue():
        if int(row.get("rank", -1)) == rank:
            return row
    raise HTTPException(status_code=404, detail=f"Rank {rank} not found")


@app.get("/checkpoints")
def checkpoints() -> dict[str, Any]:
    """Return enriched traffic checkpoint records."""
    rows = _require_checkpoints()
    return {"total": len(rows), "checkpoints": rows}


@app.get("/dashboard")
def dashboard() -> FileResponse:
    """Return the generated dashboard HTML file."""
    path = OUTPUT_DIR / "dashboard.html"
    if not path.exists():
        raise HTTPException(status_code=503, detail="Dashboard is missing. Run main.py first.")
    return FileResponse(path)


@app.get("/stats/by-district")
def stats_by_district() -> list[dict[str, Any]]:
    """Group queue records by district with count and mean CFS."""
    df = pd.DataFrame(_require_queue())
    if df.empty:
        return []
    grouped = df.groupby("district")["cfs_score"].agg(["count", "mean"]).reset_index()
    return [
        {"district": str(row["district"]), "count": int(row["count"]), "mean_cfs": round(float(row["mean"]), 2)}
        for _, row in grouped.iterrows()
    ]


@app.get("/stats/by-type")
def stats_by_type() -> list[dict[str, Any]]:
    """Group queue records by complaint type with count and mean CFS."""
    df = pd.DataFrame(_require_queue())
    if df.empty:
        return []
    grouped = df.groupby("complaint_type")["cfs_score"].agg(["count", "mean"]).reset_index()
    return [
        {"type": str(row["complaint_type"]), "count": int(row["count"]), "mean_cfs": round(float(row["mean"]), 2)}
        for _, row in grouped.iterrows()
    ]
