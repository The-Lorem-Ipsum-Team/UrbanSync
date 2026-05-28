# FILE: src/spatial_join.py
"""Spatially attach complaints to nearest traffic checkpoints."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import KDTree


OUTPUT_DIR = Path("outputs")


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return the haversine distance between two WGS84 coordinates in kilometers."""
    radius = 6371.0
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    delta_phi = math.radians(float(lat2) - float(lat1))
    delta_lambda = math.radians(float(lng2) - float(lng1))
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def load_district_bounds(bounds_path: str | Path) -> dict[str, dict[str, float]]:
    """Load district bounding boxes from JSON."""
    return json.loads(Path(bounds_path).read_text(encoding="utf-8"))


def district_to_centroid(district_str: object, district_bounds: dict[str, dict[str, float]]) -> tuple[float, float]:
    """Convert a district name to the centroid of its configured bounding box."""
    district = str(district_str).strip()
    bounds = district_bounds.get(district) or district_bounds["ไม่ระบุ"]
    lat = (float(bounds["lat_min"]) + float(bounds["lat_max"])) / 2
    lng = (float(bounds["lng_min"]) + float(bounds["lng_max"])) / 2
    return lat, lng


def build_complaint_coordinates(complaints_df: pd.DataFrame, district_bounds: dict[str, dict[str, float]]) -> np.ndarray:
    """Build an N by 2 array of approximate complaint coordinates."""
    coords = [district_to_centroid(row.get("เขต", "ไม่ระบุ"), district_bounds) for _, row in complaints_df.iterrows()]
    return np.array(coords, dtype=float)


def join_complaints_to_traffic(
    complaints_df: pd.DataFrame,
    traffic_df: pd.DataFrame,
    district_bounds_path: str | Path,
) -> pd.DataFrame:
    """Attach nearest checkpoint and traffic fields to each complaint row."""
    if traffic_df.empty:
        raise ValueError("traffic_df is empty; cannot run spatial join")
    result = complaints_df.copy()
    bounds = load_district_bounds(district_bounds_path)
    complaint_coords = build_complaint_coordinates(result, bounds)
    checkpoint_coords = traffic_df[["Lat", "Lng"]].astype(float).values
    distances, indices = KDTree(checkpoint_coords).query(complaint_coords, k=1)
    nearest = traffic_df.iloc[indices].reset_index(drop=True)
    result = result.reset_index(drop=True)
    result["nearest_checkpoint_id"] = nearest["checkpoint_id"].astype(str)
    result["checkpoint_road_name"] = nearest["เส้นทาง"].astype(str)
    result["checkpoint_location"] = nearest["ตำแหน่งติดตั้งเครื่องวัด"].astype(str)
    result["checkpoint_distance_km"] = (distances * 111.0).round(1)
    result["traffic_multiplier"] = nearest["traffic_multiplier"].astype(float)
    result["daily_vehicle_count"] = nearest["รวมต่อวัน"].astype(int)
    result["weighted_volume"] = nearest["weighted_volume"].astype(float)
    result["checkpoint_lat"] = nearest["Lat"].astype(float)
    result["checkpoint_lng"] = nearest["Lng"].astype(float)
    print(f"Spatial join complete. {len(result)} complaints matched.")
    print(f"Mean distance to nearest checkpoint: {float(result['checkpoint_distance_km'].mean()):.1f} km")
    print("Complaints by district:")
    print(result["เขต"].value_counts().to_string())
    return result


def run_spatial_join(complaints_path: str | Path, traffic_path: str | Path, district_bounds_path: str | Path) -> pd.DataFrame:
    """Load enriched CSV files, run nearest-checkpoint join, and save CSV output."""
    complaints_df = pd.read_csv(complaints_path)
    traffic_df = pd.read_csv(traffic_path)
    joined = join_complaints_to_traffic(complaints_df, traffic_df, district_bounds_path)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    joined.to_csv(OUTPUT_DIR / "complaints_with_traffic.csv", index=False, encoding="utf-8-sig")
    print(f"Spatial output saved -> {OUTPUT_DIR / 'complaints_with_traffic.csv'}")
    return joined
