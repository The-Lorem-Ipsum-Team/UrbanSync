# FILE: src/traffic_processor.py
"""Traffic dashboard loading, tiering, and video cross-validation."""

from __future__ import annotations

import difflib
import math
from pathlib import Path

import numpy as np
import pandas as pd


OUTPUT_DIR = Path("outputs")


def _to_int_series(series: pd.Series) -> pd.Series:
    """Convert comma-formatted numeric values to nullable integers."""
    cleaned = series.astype(str).str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(cleaned, errors="coerce").fillna(0).astype(int)


def load_traffic_data(csv_path: str | Path) -> pd.DataFrame:
    """Load traffic CSV, normalize columns, and return clean checkpoint rows."""
    path = Path(csv_path)
    df = pd.read_csv(path)
    df.columns = [str(col).strip() for col in df.columns]
    if "Lng" not in df.columns and "Lag" in df.columns:
        df = df.rename(columns={"Lag": "Lng"})
    for column in ["Car", "Motorcycle", "Truck", "รวมต่อวัน"]:
        if column in df.columns:
            df[column] = _to_int_series(df[column])
    df["Lat"] = pd.to_numeric(df["Lat"], errors="coerce")
    df["Lng"] = pd.to_numeric(df["Lng"], errors="coerce")
    df = df.dropna(subset=["Lat", "Lng"])
    df = df[(df["Lat"] != 0) & (df["Lng"] != 0)].copy()
    df["checkpoint_id"] = "CP_" + df["ที่"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(2)
    print(f"Traffic columns: {list(df.columns)}")
    if not df.empty:
        print(f"First traffic row: {df.iloc[0].to_dict()}")
    return df


def compute_weighted_volume(df: pd.DataFrame) -> pd.DataFrame:
    """Add weighted volume, traffic tier, and multiplier columns.

    Uses continuous linear scaling (1.0–3.0) rather than discrete tiers to
    avoid artificial priority cliffs between nearly-equal-volume checkpoints.
    traffic_tier column is retained for human-readable display only.
    """
    result = df.copy()
    result["weighted_volume"] = (
        result["Car"].astype(float) * 1.0
        + result["Motorcycle"].astype(float) * 0.5
        + result["Truck"].astype(float) * 3.0
    )

    # Continuous multiplier: 1.0 + (volume / 130_000) * 2.0, clamped [1.0, 3.0]
    raw_multiplier = 1.0 + (result["รวมต่อวัน"].astype(float) / 130_000) * 2.0
    result["traffic_multiplier"] = raw_multiplier.clip(lower=1.0, upper=3.0).round(3)

    # Traffic tier — for display/filtering only, does NOT drive the multiplier
    conditions = [
        result["รวมต่อวัน"] > 130000,
        result["รวมต่อวัน"] > 80000,
        result["รวมต่อวัน"] > 30000,
    ]
    result["traffic_tier"] = np.select(conditions, ["critical", "high", "medium"], default="low")

    print("Traffic tier distribution:")
    print(result["traffic_tier"].value_counts().to_string())

    min_mult = result["traffic_multiplier"].min()
    max_mult = result["traffic_multiplier"].max()
    mean_mult = result["traffic_multiplier"].mean()
    print("Traffic multipliers assigned (continuous 1.0–3.0):")
    print(f"  Range: {min_mult:.3f} – {max_mult:.3f}")
    print(f"  Mean:  {mean_mult:.3f}")
    return result


def _match_location(query: str, candidates: pd.Series) -> tuple[int | None, float]:
    """Return the best fuzzy match index and score for a location query."""
    best_index: int | None = None
    best_ratio = 0.0
    for index, candidate in candidates.items():
        ratio = difflib.SequenceMatcher(None, query, str(candidate)).ratio()
        if ratio > best_ratio:
            best_index = int(index)
            best_ratio = ratio
    return best_index, best_ratio


def cross_validate_with_video(traffic_df: pd.DataFrame, video_csv_path: str | Path) -> pd.DataFrame:
    """Attach video correction factors when video count output is available."""
    path = Path(video_csv_path)
    result = traffic_df.copy()
    result["matched_video_id"] = None
    result["correction_factor"] = math.nan
    if not path.exists():
        print(f"Warning: video counts file not found: {path}")
        result["correction_factor"] = 1.0
        result["estimated_true_volume"] = result["รวมต่อวัน"].astype(int)
        return result

    video_df = pd.read_csv(path)
    if video_df.empty:
        print("Warning: video counts file is empty.")
        result["correction_factor"] = 1.0
        result["estimated_true_volume"] = result["รวมต่อวัน"].astype(int)
        return result

    # Fix 3: filter for reliably-extrapolated rows before computing correction factors
    if "extrapolation_reliable" in video_df.columns:
        reliable_df = video_df[video_df["extrapolation_reliable"] == True].copy()
    else:
        reliable_df = video_df  # backward compat if column absent

    n_reliable = len(reliable_df)
    n_total = len(video_df)
    print(f"Cross-validation: using {n_reliable}/{n_total} videos (reliable extrapolation).")
    if n_reliable == 0:
        print("  ⚠ No reliable extrapolations found. Correction factor defaulted to 1.0.")
        print("    Re-run with larger --max-frames for accurate cross-validation.")
        result["correction_factor"] = 1.0
        result["estimated_true_volume"] = result["รวมต่อวัน"].astype(int)
        return result

    candidates = result["เส้นทาง"].astype(str) + " " + result["ตำแหน่งติดตั้งเครื่องวัด"].astype(str)
    matches: list[dict[str, object]] = []
    for _, row in reliable_df.iterrows():
        location_name = str(row.get("location_name", ""))
        matched_index, ratio = _match_location(location_name, candidates)
        if matched_index is None or ratio <= 0.35:
            continue
        video_total = pd.to_numeric(row.get("bidirectional_total", row.get("total_unique_vehicles", 0)), errors="coerce")
        dashboard_total = pd.to_numeric(result.loc[matched_index, "รวมต่อวัน"], errors="coerce")
        if pd.isna(video_total) or pd.isna(dashboard_total) or float(dashboard_total) <= 0:
            continue
        factor = float(np.clip(float(video_total) / float(dashboard_total), 0.5, 5.0))
        result.loc[matched_index, "matched_video_id"] = str(row.get("video_id", row.get("source_file", "")))
        result.loc[matched_index, "correction_factor"] = factor
        matches.append(
            {
                "checkpoint": result.loc[matched_index, "checkpoint_id"],
                "video": row.get("video_id", row.get("source_file", "")),
                "correction_factor": round(factor, 2),
            }
        )

    mean_factor = float(result["correction_factor"].dropna().mean()) if result["correction_factor"].notna().any() else 1.0
    result["correction_factor"] = result["correction_factor"].fillna(mean_factor)
    result["estimated_true_volume"] = (result["รวมต่อวัน"].astype(float) * result["correction_factor"]).round().astype(int)
    print(f"Matched {len(matches)}/{len(result)} checkpoints. Mean correction factor: {mean_factor:.2f}")
    if matches:
        print(pd.DataFrame(matches).to_string(index=False))
    return result


def process_traffic_data(csv_path: str | Path, video_counts_path: str | Path | None = None) -> pd.DataFrame:
    """Run traffic loading, tiering, optional video validation, and save CSV output."""
    df = compute_weighted_volume(load_traffic_data(csv_path))
    if video_counts_path is not None:
        df = cross_validate_with_video(df, video_counts_path)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_DIR / "traffic_enriched.csv", index=False, encoding="utf-8-sig")
    print(f"Traffic output saved -> {OUTPUT_DIR / 'traffic_enriched.csv'}")
    return df
