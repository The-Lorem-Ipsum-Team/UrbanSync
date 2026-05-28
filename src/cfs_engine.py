# FILE: src/cfs_engine.py
"""Civic Friction Score computation and ranked queue exports."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


OUTPUT_DIR = Path("outputs")


def compute_cfs(df: pd.DataFrame) -> pd.DataFrame:
    """Filter open complaints and compute CFS score, tier, rank, and ordering."""
    # ── CFS WEIGHTING DESIGN NOTE ─────────────────────────────────────────────────────
    # CFS = severity_score (1–10) × traffic_multiplier (1.0–3.0)
    #
    # Severity has a wider range (10x) than the multiplier (3x). This is
    # intentional: the TYPE of infrastructure failure is the primary dispatch
    # signal. A flood or collapsed road affects surrounding road capacity
    # beyond just the nearest checkpoint — its impact is not bounded by one
    # sensor location.
    #
    # The traffic multiplier is the LOCATION TIEBREAKER: between two complaints
    # of equal severity, crews are directed to the higher-volume corridor first.
    #
    # Example — two identical potholes (severity = 9):
    #   ถ.กสิกรทุ่งสร้าง (160k/day, mult=3.0) → CFS = 27.0  ← dispatched first
    #   Quiet residential soi (20k/day, mult=1.0) → CFS = 9.0
    #
    # Max possible CFS = 30.0 (severity=10, mult=3.0)
    # Min possible CFS =  1.0 (severity=1,  mult=1.0)
    # ──────────────────────────────────────────────────────────────────────
    open_df = df[df["is_open"] == True].copy()
    open_df["cfs_score"] = (open_df["severity_score"].astype(float) * open_df["traffic_multiplier"].astype(float)).round(2)
    conditions = [
        open_df["cfs_score"] >= 24,
        open_df["cfs_score"] >= 15,
        open_df["cfs_score"] >= 8,
    ]
    open_df["cfs_tier"] = np.select(conditions, ["critical", "high", "medium"], default="low")
    open_df["priority_rank"] = open_df["cfs_score"].rank(ascending=False, method="first").astype(int)
    open_df = open_df.sort_values("priority_rank").reset_index(drop=True)
    print("CFS tier distribution:")
    print(open_df["cfs_tier"].value_counts().to_string())
    print()
    print("CFS weighting:")
    print(f"  Mean severity score    : {open_df['severity_score'].mean():.2f} / 10")
    print(f"  Mean traffic multiplier: {open_df['traffic_multiplier'].mean():.2f} / 3.0")
    print(f"  Mean CFS score         : {open_df['cfs_score'].mean():.2f} / 30.0")
    print("  Severity is primary signal. Multiplier is location tiebreaker.")
    return open_df


def compute_fifo_vs_cfs_comparison(df: pd.DataFrame) -> pd.DataFrame:
    """Compare oldest-first FIFO ranking with CFS priority ranking and save CSV."""
    result = df.copy()
    date_col = "date_received" if "date_received" in result.columns else "วันที่รับเรื่อง"
    result["วันที่รับเรื่อง_sort"] = pd.to_datetime(result[date_col], errors="coerce")
    result["fifo_rank"] = result["วันที่รับเรื่อง_sort"].rank(ascending=True, method="first").astype(int)
    result["rank_change"] = result["fifo_rank"] - result["priority_rank"]
    result["rank_change_label"] = np.select(
        [result["rank_change"] > 100, result["rank_change"] > 20, result["rank_change"] < -20],
        ["major upgrade", "upgrade", "downgrade"],
        default="similar",
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result.drop(columns=["วันที่รับเรื่อง_sort"]).to_csv(OUTPUT_DIR / "fifo_vs_cfs_comparison.csv", index=False, encoding="utf-8-sig")
    print("Biggest beneficiaries of CFS vs FIFO:")
    columns = [col for col in ["เลขคำร้อง", "ประเภทคำร้อง", "เขต", "priority_rank", "fifo_rank", "rank_change", "cfs_score"] if col in result.columns]
    if columns:
        print(result.sort_values("rank_change", ascending=False).head(10)[columns].to_string(index=False))
    return result.drop(columns=["วันที่รับเรื่อง_sort"])


def _safe_int(value: Any, default: int = 0) -> int:
    """Convert value to int with a default for missing values."""
    if pd.isna(value):
        return default
    return int(value)


def format_queue_record(row: pd.Series) -> dict[str, Any]:
    """Convert a ranked DataFrame row into the public queue record schema."""
    return {
        "rank": int(row["priority_rank"]),
        "complaint_id": str(row["เลขคำร้อง"]),
        "complaint_type": str(row["ประเภทคำร้อง"]),
        "description": str(row["เรื่องร้องทุกข์"]),
        "district": str(row["เขต"]),
        "community": str(row["ชุมชน"]),
        "days_open": _safe_int(row["days_open"]),
        "severity_score": int(row["severity_score"]),
        "traffic_multiplier": float(row["traffic_multiplier"]),
        "cfs_score": float(row["cfs_score"]),
        "cfs_tier": str(row["cfs_tier"]),
        "nearest_road": str(row["checkpoint_road_name"]),
        "daily_vehicles": _safe_int(row["daily_vehicle_count"]),
        "date_received": str(row["วันที่รับเรื่อง"]),
        "checkpoint_lat": float(row["checkpoint_lat"]) if "checkpoint_lat" in row and not pd.isna(row["checkpoint_lat"]) else None,
        "checkpoint_lng": float(row["checkpoint_lng"]) if "checkpoint_lng" in row and not pd.isna(row["checkpoint_lng"]) else None,
    }


def generate_queue_output(ranked_df: pd.DataFrame) -> dict[str, Any]:
    """Write ranked queue JSON/CSV files and return the queue payload."""
    queue = [format_queue_record(row) for _, row in ranked_df.iterrows()]
    result = {"generated_at": dt.datetime.now().isoformat(), "total_open": len(ranked_df), "queue": queue}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "ranked_queue.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(queue).to_csv(OUTPUT_DIR / "ranked_queue.csv", index=False, encoding="utf-8-sig")
    if queue:
        top = queue[0]
        print(f"Queue saved. Top complaint: {top['complaint_type']} | CFS: {top['cfs_score']} | District: {top['district']}")
    else:
        print("Queue saved. No open complaints found.")
    return result


def compute_statistics(df: pd.DataFrame, full_df: pd.DataFrame) -> dict[str, Any]:
    """Compute summary dashboard/API statistics and save JSON."""
    days = df["days_open"].dropna() if "days_open" in df else pd.Series(dtype=float)
    stats = {
        "total_open": len(df),
        "total_closed": int((full_df["is_open"] == False).sum()),
        "critical_count": int((df["cfs_tier"] == "critical").sum()),
        "high_count": int((df["cfs_tier"] == "high").sum()),
        "medium_count": int((df["cfs_tier"] == "medium").sum()),
        "low_count": int((df["cfs_tier"] == "low").sum()),
        "mean_days_open": round(float(days.mean()), 1) if not days.empty else 0.0,
        "max_days_open": int(days.max()) if not days.empty else 0,
        "top_complaint_type": str(df["ประเภทคำร้อง"].value_counts().index[0]) if not df.empty else "",
        "top_affected_district": str(df["เขต"].value_counts().index[0]) if not df.empty else "",
        "mean_cfs_score": round(float(df["cfs_score"].mean()), 2) if not df.empty else 0.0,
        "max_cfs_score": round(float(df["cfs_score"].max()), 2) if not df.empty else 0.0,
        "severity_vs_traffic_note": (
            "The CFS formula is severity_score (1-10) * traffic_multiplier (1.0-3.0). "
            "Because severity_score has a 10x range and traffic_multiplier has a 3x range, "
            "severity naturally dominates the priority ranking. This design choice ensures that "
            "high-hazard incidents (e.g. major flooding or failed traffic lights) are prioritized "
            "over minor issues, while traffic volume acts as a strong multiplier and tie-breaker."
        ),
        "design_notes": {
            "cfs_formula": "CFS = severity_score x traffic_multiplier",
            "severity_range": "1\u201310 (complaint type + Thai keyword boost)",
            "multiplier_range": "1.0\u20133.0 (continuous linear scale)",
            "dominant_factor": "severity_score",
            "rationale": (
                "Complaint type is the primary dispatch signal. "
                "Infrastructure failures like floods affect surrounding road capacity "
                "beyond a single checkpoint. Traffic volume is the tiebreaker between "
                "equal-severity complaints, directing crews to higher-volume corridors."
            ),
            "max_possible_cfs": 30.0,
            "min_possible_cfs": 1.0,
        },
        "generated_at": dt.datetime.now().isoformat(),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "statistics.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def run_cfs_engine(input_path: str | Path) -> pd.DataFrame:
    """Load joined complaint data, compute CFS outputs, and return ranked rows."""
    full_df = pd.read_csv(input_path)
    if "is_open" in full_df.columns:
        full_df["is_open"] = full_df["is_open"].astype(str).str.lower().isin(["true", "1", "yes"])
    ranked = compute_cfs(full_df)
    ranked = compute_fifo_vs_cfs_comparison(ranked)
    generate_queue_output(ranked)
    compute_statistics(ranked, full_df)
    return ranked
