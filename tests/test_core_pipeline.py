from __future__ import annotations

import datetime as dt
import json

import numpy as np
import pandas as pd


def test_traffic_weighted_volume_and_multiplier_thresholds() -> None:
    from src.traffic_processor import compute_weighted_volume

    df = pd.DataFrame(
        {
            "Car": [100, 100, 100, 100],
            "Motorcycle": [20, 20, 20, 20],
            "Truck": [10, 10, 10, 10],
            "รวมต่อวัน": [130001, 90000, 50000, 10000],
        }
    )

    result = compute_weighted_volume(df)

    assert result["weighted_volume"].tolist() == [140.0, 140.0, 140.0, 140.0]
    assert result["traffic_tier"].tolist() == ["critical", "high", "medium", "low"]
    assert result["traffic_multiplier"].tolist() == [3.0, 2.0, 1.5, 1.0]


def test_parse_thai_date_converts_buddhist_year_and_rejects_invalid() -> None:
    from src.complaint_processor import parse_thai_date

    assert parse_thai_date("09/01/2567") == dt.date(2024, 1, 9)
    assert parse_thai_date("bad value") is None
    assert parse_thai_date(np.nan) is None


def test_apply_severity_scores_uses_partial_type_match_and_max_keyword_boost(tmp_path) -> None:
    from src.complaint_processor import apply_severity_scores

    severity_path = tmp_path / "severity_lookup.json"
    keyword_path = tmp_path / "severity_keywords.json"
    severity_path.write_text(json.dumps({"ถนน": 9}, ensure_ascii=False), encoding="utf-8")
    keyword_path.write_text(json.dumps({"หลุมบ่อ": 2, "ด่วน": 3}, ensure_ascii=False), encoding="utf-8")
    df = pd.DataFrame(
        {
            "ประเภทคำร้อง": ["ซ่อมถนนในชุมชน", "อื่น"],
            "เรื่องร้องทุกข์": ["หลุมบ่อ ด่วน", "เรื่องทั่วไป"],
        }
    )

    result = apply_severity_scores(df, severity_path, keyword_path)

    assert result["base_severity"].tolist() == [9, 3]
    assert result["keyword_boost"].tolist() == [3, 0]
    assert result["severity_score"].tolist() == [10, 3]


def test_spatial_join_attaches_nearest_checkpoint_fields(tmp_path) -> None:
    from src.spatial_join import join_complaints_to_traffic

    bounds_path = tmp_path / "district_bounds.json"
    bounds_path.write_text(
        json.dumps(
            {
                "เขต 1": {"lat_min": 16.0, "lat_max": 16.2, "lng_min": 102.0, "lng_max": 102.2},
                "ไม่ระบุ": {"lat_min": 16.4, "lat_max": 16.6, "lng_min": 102.4, "lng_max": 102.6},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    complaints = pd.DataFrame({"เขต": ["เขต 1"]})
    traffic = pd.DataFrame(
        {
            "checkpoint_id": ["CP_01", "CP_02"],
            "Lat": [16.1, 16.5],
            "Lng": [102.1, 102.5],
            "เส้นทาง": ["Road A", "Road B"],
            "ตำแหน่งติดตั้งเครื่องวัด": ["Loc A", "Loc B"],
            "traffic_multiplier": [2.0, 1.0],
            "รวมต่อวัน": [90000, 10000],
            "weighted_volume": [120000.0, 15000.0],
        }
    )

    result = join_complaints_to_traffic(complaints, traffic, bounds_path)

    assert result.loc[0, "nearest_checkpoint_id"] == "CP_01"
    assert result.loc[0, "checkpoint_road_name"] == "Road A"
    assert result.loc[0, "traffic_multiplier"] == 2.0


def test_cfs_ranking_and_queue_record_generation(tmp_path, monkeypatch) -> None:
    from src import cfs_engine
    from src.cfs_engine import compute_cfs, generate_queue_output

    monkeypatch.setattr(cfs_engine, "OUTPUT_DIR", tmp_path)

    df = pd.DataFrame(
        {
            "is_open": [True, True, False],
            "severity_score": [10, 5, 10],
            "traffic_multiplier": [3.0, 1.5, 3.0],
            "เลขคำร้อง": ["A", "B", "C"],
            "ประเภทคำร้อง": ["น้ำท่วม", "ไฟฟ้า", "ถนน"],
            "เรื่องร้องทุกข์": ["น้ำท่วมถนน", "ไฟดับ", "ปิดแล้ว"],
            "เขต": ["เขต 1", "เขต 2", "เขต 3"],
            "ชุมชน": ["ชุมชน A", "ชุมชน B", "ชุมชน C"],
            "days_open": [2, 4, None],
            "checkpoint_road_name": ["Road A", "Road B", "Road C"],
            "daily_vehicle_count": [150000, 50000, 150000],
            "วันที่รับเรื่อง": [dt.date(2024, 1, 1), dt.date(2024, 1, 2), dt.date(2024, 1, 3)],
        }
    )

    ranked = compute_cfs(df)
    output = generate_queue_output(ranked)

    assert ranked["เลขคำร้อง"].tolist() == ["A", "B"]
    assert ranked["cfs_tier"].tolist() == ["critical", "low"]
    assert output["total_open"] == 2
    assert output["queue"][0]["rank"] == 1
    assert output["queue"][0]["cfs_score"] == 30.0
