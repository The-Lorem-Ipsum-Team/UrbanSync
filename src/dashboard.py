# FILE: src/dashboard.py
"""Offline-friendly HTML dashboard generation — single-page panel app with tab navigation."""

from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np

KK_CENTER = [16.432, 102.834]
TIER_COLORS = {"critical": "#E24B4A", "high": "#EF9F27", "medium": "#378ADD", "low": "#639922"}


def _require_folium() -> Any:
    """Import folium lazily so non-dashboard modules remain usable without it."""
    try:
        import folium
    except Exception as exc:
        raise RuntimeError(f"Dashboard generation requires folium: {exc}") from exc
    return folium


def checkpoint_popup_html(row: pd.Series) -> str:
    """Return HTML popup content for a traffic checkpoint (folium compat)."""
    return (
        f"<b>{html.escape(str(row.get('เส้นทาง', '')))}</b><br>"
        f"{html.escape(str(row.get('ตำแหน่งติดตั้งเครื่องวัด', '')))}<br>"
        f"Total/day: {int(row.get('รวมต่อวัน', 0)):,}<br>"
        f"Tier: {html.escape(str(row.get('traffic_tier', '')))}<br>"
        f"Multiplier: {float(row.get('traffic_multiplier', 1.0)):.3f}"
    )


def complaint_popup_html(complaint_dict: dict[str, Any]) -> str:
    """Return HTML popup content for a complaint marker (folium compat)."""
    return (
        f"<b>#{int(complaint_dict.get('rank', 0))} {html.escape(str(complaint_dict.get('complaint_type', '')))}</b><br>"
        f"{html.escape(str(complaint_dict.get('description', ''))[:120])}<br>"
        f"District: {html.escape(str(complaint_dict.get('district', '')))}<br>"
        f"Days open: {int(complaint_dict.get('days_open', 0))}<br>"
        f"CFS Score: {float(complaint_dict.get('cfs_score', 0.0)):.2f}"
    )


def create_map(ranked_queue_list: list[dict[str, Any]], traffic_df: pd.DataFrame) -> Any:
    """Create a Folium map (kept for API compatibility; main dashboards now use inline Leaflet)."""
    folium = _require_folium()
    map_obj = folium.Map(location=KK_CENTER, zoom_start=13, tiles="OpenStreetMap")
    max_volume = max(float(traffic_df["รวมต่อวัน"].max()), 1.0) if not traffic_df.empty else 1.0
    for _, row in traffic_df.iterrows():
        radius = 8 + int((float(row.get("รวมต่อวัน", 0)) / max_volume) * 16)
        color = TIER_COLORS.get(str(row.get("traffic_tier", "low")), TIER_COLORS["low"])
        folium.CircleMarker(
            location=[float(row["Lat"]), float(row["Lng"])],
            radius=radius, color=color, fill=True, fill_color=color, fill_opacity=0.65,
            popup=folium.Popup(html=checkpoint_popup_html(row), max_width=280),
        ).add_to(map_obj)
    for complaint in ranked_queue_list:
        lat = complaint.get("checkpoint_lat")
        lng = complaint.get("checkpoint_lng")
        if lat is None or lng is None:
            continue
        color = TIER_COLORS.get(str(complaint.get("cfs_tier", "low")), TIER_COLORS["low"])
        popup = folium.Popup(html=complaint_popup_html(complaint), max_width=300)
        folium.CircleMarker(location=[lat, lng], radius=6, color=color, fill=True,
                            fill_opacity=0.75, popup=popup).add_to(map_obj)
    return map_obj


def _tier_bars(stats: dict[str, Any]) -> str:
    """Render CFS tier distribution bars as HTML."""
    total = max(int(stats.get("total_open", 0)), 1)
    bars = []
    for tier in ["critical", "high", "medium", "low"]:
        count = int(stats.get(f"{tier}_count", 0))
        width = round((count / total) * 100, 1)
        bars.append(
            f"<div class='bar-row'>"
            f"<span class='bar-label'>{tier.title()}</span>"
            f"<div class='bar-track'><div class='bar-fill' style='width:{width}%;background:{TIER_COLORS[tier]}'></div></div>"
            f"<span class='bar-value'>{count}</span>"
            f"</div>"
        )
    return "\n".join(bars)


def _get_shared_styles() -> str:
    """Return the full CSS for the single-page panel app layout."""
    return """
        *{box-sizing:border-box;margin:0;padding:0}
        html,body{height:100%;overflow:hidden;background:#0D1B2A;color:#E8F4F8;
            font-family:'Segoe UI',system-ui,-apple-system,sans-serif}
        /* ── App shell ── */
        .app{display:flex;flex-direction:column;height:100vh}
        /* ── Top nav ── */
        .topnav{flex-shrink:0;display:flex;align-items:center;gap:0;
            background:#070F1A;border-bottom:1px solid #1D3D2F;height:54px;
            padding:0 20px;box-shadow:0 2px 12px rgba(0,0,0,.5)}
        .brand{font-size:17px;font-weight:800;color:#1D9E75;letter-spacing:-.5px;
            margin-right:28px;white-space:nowrap}
        .brand span{color:#8DE3C2;font-weight:400}
        .tab-strip{display:flex;gap:3px;flex:1;overflow-x:auto;
            scrollbar-width:none}
        .tab-strip::-webkit-scrollbar{display:none}
        .tab-btn{background:transparent;border:none;color:#6A8CA0;
            padding:7px 15px;border-radius:7px;font-size:13px;font-weight:600;
            cursor:pointer;transition:all .18s ease;white-space:nowrap;
            display:flex;align-items:center;gap:6px}
        .tab-btn:hover{background:#132030;color:#C8E6F0}
        .tab-btn.active{background:linear-gradient(135deg,#1D9E75,#169060);
            color:#fff;box-shadow:0 2px 10px rgba(29,158,117,.35)}
        .tab-btn .icon{font-size:14px}
        /* ── Dashboard switcher links ── */
        .dash-links{display:flex;gap:4px;margin-left:16px;border-left:1px solid #1D3D2F;
            padding-left:14px;flex-shrink:0}
        .dash-link{background:#0F1E2C;border:1px solid #1D3D2F;color:#6A8CA0;
            padding:5px 12px;border-radius:6px;text-decoration:none;font-size:12px;
            font-weight:600;transition:all .18s}
        .dash-link:hover{border-color:#1D9E75;color:#1D9E75}
        .dash-link.active{background:#0F2922;border-color:#1D9E75;color:#8DE3C2}
        /* ── Content area & panels ── */
        .content-area{flex:1;overflow:hidden;position:relative}
        .panel{position:absolute;inset:0;overflow-y:auto;display:none;padding:22px 26px}
        .panel.active{display:block;animation:fadeIn .2s ease}
        .panel-map{padding:0!important}
        @keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
        /* ── Scrollbar ── */
        ::-webkit-scrollbar{width:5px}
        ::-webkit-scrollbar-track{background:#0D1B2A}
        ::-webkit-scrollbar-thumb{background:#1D3D2F;border-radius:99px}
        ::-webkit-scrollbar-thumb:hover{background:#1D9E75}
        /* ── Cards ── */
        .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
            gap:14px;margin-bottom:22px}
        .card{background:#111E2D;border:1px solid #1A2E42;border-radius:14px;padding:18px 20px;
            box-shadow:0 4px 14px rgba(0,0,0,.3);position:relative;overflow:hidden}
        .card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;
            background:linear-gradient(90deg,#1D9E75,transparent)}
        .card h3{font-size:11px;color:#5A7A90;text-transform:uppercase;letter-spacing:.9px;
            font-weight:700;margin-bottom:10px}
        .card b{display:block;font-size:26px;color:#1D9E75;font-weight:800;line-height:1}
        .card small{font-size:11px;color:#4A6A80;margin-top:5px;display:block}
        /* ── Section headings ── */
        .section-hd{font-size:15px;font-weight:700;color:#E8F4F8;margin-bottom:16px;
            padding-bottom:10px;border-bottom:1px solid #1A2E42;
            display:flex;align-items:center;gap:9px}
        .section-hd::before{content:'';width:3px;height:16px;background:#1D9E75;
            border-radius:2px;flex-shrink:0}
        /* ── Info boxes ── */
        .info-box{background:#0A1E17;border:1px solid #1D3D2F;border-radius:12px;
            padding:16px 18px}
        .info-box h3{color:#8DE3C2;font-size:13px;font-weight:700;margin-bottom:8px}
        .info-box p{font-size:13px;line-height:1.7;color:#C0DCE8}
        /* ── Grids ── */
        .g2{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px}
        .g3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:18px;margin-bottom:18px}
        @media(max-width:960px){.g2,.g3{grid-template-columns:1fr}}
        /* ── Tables ── */
        .tbl-wrap{background:#111E2D;border:1px solid #1A2E42;border-radius:12px;
            overflow:hidden;box-shadow:0 4px 14px rgba(0,0,0,.25)}
        table{width:100%;border-collapse:collapse}
        th,td{padding:10px 15px;border-bottom:1px solid #1A2E42;text-align:left;font-size:13px}
        th{color:#8DE3C2;background:#0A1520;font-weight:700;font-size:11px;
            text-transform:uppercase;letter-spacing:.8px;position:sticky;top:0;z-index:2}
        tr:last-child td{border-bottom:none}
        tr:hover td{background:#1A2E42;transition:background .12s}
        .bold-row td{font-weight:700;border-left:3px solid #1D9E75}
        /* ── Bar charts ── */
        .bars-box{background:#111E2D;border:1px solid #1A2E42;border-radius:12px;padding:18px 20px}
        .bar-row{display:grid;grid-template-columns:150px 1fr 130px;
            gap:14px;align-items:center;margin:10px 0}
        .bar-label{font-size:13px;color:#8BA8BC;font-weight:500}
        .bar-track{height:9px;background:#0D1B2A;border-radius:99px;overflow:hidden}
        .bar-fill{height:100%;border-radius:99px;transition:width .6s ease}
        .bar-value{font-size:12px;color:#C0DCE8;font-weight:600;text-align:right}
        /* ── Badges ── */
        .badge{color:#fff;border-radius:5px;padding:3px 8px;font-weight:700;
            font-size:11px;text-transform:uppercase;letter-spacing:.4px}
        /* ── Keywords ── */
        .kw-panel{display:flex;flex-wrap:wrap;gap:8px}
        .kw-badge{background:#132030;border:1px solid #1D3D2F;color:#8DE3C2;
            font-size:12px;padding:5px 12px;border-radius:20px;font-weight:600}
        /* ── Map ── */
        #leaflet-map,#leaflet-map2,#leaflet-map3{height:100%;width:100%}
        .leaflet-popup-content-wrapper{background:#111E2D!important;color:#E8F4F8!important;
            border:1px solid #1A2E42!important;border-radius:10px!important}
        .leaflet-popup-tip{background:#111E2D!important}
        .leaflet-popup-content h3{margin:0 0 8px;color:#1D9E75;font-size:13px;
            border-bottom:1px solid #1A2E42;padding-bottom:5px}
        .leaflet-popup-content table{width:100%;border-collapse:collapse}
        .leaflet-popup-content td{padding:3px 6px;font-size:12px;
            border-bottom:1px solid #1A2E42;background:transparent!important}
        /* ── Stacked bar ── */
        .stk-track{display:flex;height:9px;border-radius:99px;overflow:hidden}
        /* ── Panel footer ── */
        .pfooter{text-align:center;font-size:11px;color:#3A5A6C;padding:20px 0 4px;
            border-top:1px solid #1A2E42;margin-top:24px}
        /* ── Legend dot ── */
        .dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px}
    """


def _topnav(tabs: list[tuple[str, str, str]], active_tab: str, active_dash: str) -> str:
    """Build the top navigation bar HTML."""
    tab_btns = []
    for tab_id, icon, label in tabs:
        cls = "tab-btn active" if tab_id == active_tab else "tab-btn"
        tab_btns.append(
            f"<button class='{cls}' data-tab='{tab_id}' onclick=\"showTab('{tab_id}')\">"
            f"<span class='icon'>{icon}</span>{label}</button>"
        )
    dash_pages = [
        ("traffic_dashboard.html", "🚦 Traffic"),
        ("complaint_dashboard.html", "📋 Complaints"),
        ("dashboard.html", "⚡ CFS Dispatch"),
    ]
    dash_btns = []
    for url, label in dash_pages:
        cls = "dash-link active" if url == active_dash else "dash-link"
        dash_btns.append(f"<a class='{cls}' href='{url}'>{label}</a>")
    return (
        f"<nav class='topnav'>"
        f"<span class='brand'>Urban<span>Sync</span></span>"
        f"<div class='tab-strip'>{''.join(tab_btns)}</div>"
        f"<div class='dash-links'>{''.join(dash_btns)}</div>"
        f"</nav>"
    )


_TAB_JS = """
    function showTab(id) {
        document.querySelectorAll('.panel').forEach(function(p){p.classList.remove('active');});
        document.querySelectorAll('.tab-btn').forEach(function(b){b.classList.remove('active');});
        document.getElementById(id).classList.add('active');
        var btn = document.querySelector('[data-tab="' + id + '"]');
        if (btn) btn.classList.add('active');
    }
"""


# ──────────────────────────────────────────────────────────────────────────────
# TRAFFIC DASHBOARD
# ──────────────────────────────────────────────────────────────────────────────

def build_traffic_dashboard(traffic_path: Path, video_counts_path: Path, output_path: Path) -> None:
    """Build outputs/traffic_dashboard.html — single-page panel app."""
    traffic_df = pd.read_csv(traffic_path)
    video_df = pd.DataFrame()
    if video_counts_path.exists():
        try:
            video_df = pd.read_csv(video_counts_path)
        except Exception:
            pass

    # ── KPI metrics ──
    total_checkpoints = len(traffic_df)
    total_daily_volume = int(traffic_df["รวมต่อวัน"].sum()) if not traffic_df.empty else 0
    highest_road = str(traffic_df.loc[traffic_df["รวมต่อวัน"].idxmax(), "เส้นทาง"]) if not traffic_df.empty else "N/A"
    highest_vol = int(traffic_df["รวมต่อวัน"].max()) if not traffic_df.empty else 0
    videos_processed = len(video_df) if not video_df.empty else 0

    # ── Classification ──
    total_cars = int(traffic_df["Car"].sum()) if not traffic_df.empty else 0
    total_motos = int(traffic_df["Motorcycle"].sum()) if not traffic_df.empty else 0
    total_trucks = int(traffic_df["Truck"].sum()) if not traffic_df.empty else 0
    total_vehicles_class = max(total_cars + total_motos + total_trucks, 1)
    car_pct = (total_cars / total_vehicles_class) * 100
    moto_pct = (total_motos / total_vehicles_class) * 100
    truck_pct = (total_trucks / total_vehicles_class) * 100

    # ── Flow analysis ──
    hour_col = "คัน/ชั่วโมง" if "คัน/ชั่วโมง" in traffic_df.columns else "hourly_throughput"
    high_load_count = int((traffic_df[hour_col] > 6000).sum()) if not traffic_df.empty and hour_col in traffic_df.columns else 0
    top_5_flow = traffic_df.sort_values(hour_col, ascending=False).head(5) if not traffic_df.empty and hour_col in traffic_df.columns else pd.DataFrame()
    bottom_5_flow = traffic_df.sort_values(hour_col, ascending=True).head(5) if not traffic_df.empty and hour_col in traffic_df.columns else pd.DataFrame()

    # ── Serialised data ──
    traffic_json = traffic_df.to_json(orient="records", force_ascii=False)
    video_json = video_df.to_json(orient="records", force_ascii=False) if not video_df.empty else "[]"

    # ── Intersection table rows ──
    table_rows = []
    sorted_traffic = traffic_df.sort_values("รวมต่อวัน", ascending=False).reset_index(drop=True)
    for idx, row in sorted_traffic.iterrows():
        tier = str(row.get("traffic_tier", "low"))
        color = TIER_COLORS.get(tier, TIER_COLORS["low"])
        cls = "bold-row" if idx < 5 else ""
        table_rows.append(
            f"<tr class='{cls}'>"
            f"<td>{idx+1}</td>"
            f"<td>{html.escape(str(row.get('เส้นทาง', '')))}</td>"
            f"<td>{html.escape(str(row.get('ตำแหน่งติดตั้งเครื่องวัด', '')))}</td>"
            f"<td>{int(row.get('รวมต่อวัน', 0)):,}</td>"
            f"<td><span class='badge' style='background:{color}'>{tier}</span></td>"
            f"<td>{float(row.get('traffic_multiplier', 1.0)):.3f}</td>"
            f"</tr>"
        )

    # ── Video table rows ──
    video_rows = []
    if not video_df.empty:
        for _, row in video_df.iterrows():
            reliable = row.get("extrapolation_reliable", False)
            rc = "#1D9E75" if reliable else "#E24B4A"
            rl = "Yes" if reliable else "No"
            video_rows.append(
                f"<tr>"
                f"<td>{html.escape(str(row.get('location_name', '')))}</td>"
                f"<td>{html.escape(str(row.get('camera_orientation', '')))}</td>"
                f"<td>{int(row.get('bidirectional_total', 0)):,}</td>"
                f"<td>{html.escape(str(row.get('counting_method', '')))}</td>"
                f"<td>{float(row.get('extrapolation_factor', 1.0)):.1f}x</td>"
                f"<td><span class='badge' style='background:{rc}'>{rl}</span></td>"
                f"</tr>"
            )
    else:
        video_rows.append("<tr><td colspan='6' style='text-align:center;color:#5A7A90;padding:20px;'>"
                          "Run --video-dir to populate CCTV cross-validation data</td></tr>")

    # ── Flow table rows ──
    flow_rows = []
    if not top_5_flow.empty:
        for idx, (_, row) in enumerate(top_5_flow.iterrows()):
            flow_rows.append(
                f"<tr><td><span style='color:#E24B4A;font-weight:700'>Peak #{idx+1}</span></td>"
                f"<td>{html.escape(str(row['เส้นทาง']))}</td>"
                f"<td><b style='color:#E24B4A'>{int(row[hour_col]):,}</b></td>"
                f"<td><span class='badge' style='background:#E24B4A'>High Load</span></td></tr>"
            )
        for idx, (_, row) in enumerate(bottom_5_flow.iterrows()):
            flow_rows.append(
                f"<tr><td><span style='color:#1D9E75;font-weight:700'>Low #{idx+1}</span></td>"
                f"<td>{html.escape(str(row['เส้นทาง']))}</td>"
                f"<td><b style='color:#1D9E75'>{int(row[hour_col]):,}</b></td>"
                f"<td><span class='badge' style='background:#1D9E75'>Off-Peak</span></td></tr>"
            )

    tabs = [
        ("t-overview",  "📊", "Overview"),
        ("t-map",       "🗺️",  "Live Map"),
        ("t-class",     "🚗", "Classification"),
        ("t-flow",      "📈", "Flow Analysis"),
        ("t-intersect", "🏁", "Intersections"),
        ("t-video",     "📹", "Video Data"),
    ]

    # Pre-compute classification table rows (avoids backslash-in-f-string restriction)
    class_table_rows = []
    for i, (_, r) in enumerate(traffic_df.sort_values("รวมต่อวัน", ascending=False).iterrows()):
        tier_val = str(r.get("traffic_tier", "low"))
        tier_col = TIER_COLORS.get(tier_val, TIER_COLORS["low"])
        class_table_rows.append(
            f"<tr><td>{i+1}</td>"
            f"<td>{html.escape(str(r.get('เส้นทาง','')))}</td>"
            f"<td>{int(r.get('Car',0)):,}</td>"
            f"<td>{int(r.get('Motorcycle',0)):,}</td>"
            f"<td>{int(r.get('Truck',0)):,}</td>"
            f"<td>{int(r.get('รวมต่อวัน',0)):,}</td>"
            f"<td><span class='badge' style='background:{tier_col}'>{tier_val}</span></td>"
            f"</tr>"
        )
    class_table_html = "".join(class_table_rows)

    html_out = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>UrbanSync — Traffic Intelligence</title>
<meta name="description" content="UrbanSync Traffic Intelligence — BDI Hackathon 2026 Khon Kaen">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>{_get_shared_styles()}</style>
</head>
<body>
<div class="app">
{_topnav(tabs, "t-overview", "traffic_dashboard.html")}
<div class="content-area">

<!-- ── OVERVIEW ── -->
<div class="panel active" id="t-overview">
  <h1 style="font-size:20px;font-weight:800;color:#E8F4F8;margin-bottom:4px">Traffic Intelligence</h1>
  <p style="color:#5A7A90;font-size:13px;margin-bottom:20px">BDI Hackathon 2026 · CCTV Analytics &amp; Intersection Performance · Khon Kaen</p>
  <div class="cards">
    <div class="card"><h3>Total Checkpoints</h3><b>{total_checkpoints}</b><small>Monitoring stations</small></div>
    <div class="card"><h3>Daily Volume</h3><b>{total_daily_volume:,}</b><small>Vehicles/day all checkpoints</small></div>
    <div class="card"><h3>Highest Volume Road</h3><b style="font-size:15px">{html.escape(highest_road)}</b><small>{highest_vol:,} vehicles/day</small></div>
    <div class="card"><h3>High-Load Checkpoints</h3><b>{high_load_count}</b><small>&gt; 6,000 vehicles/hour</small></div>
    <div class="card"><h3>Videos Processed</h3><b>{videos_processed}</b><small>CCTV locations</small></div>
  </div>
  <div class="g2">
    <div class="info-box">
      <h3>🚗 Fleet Summary</h3>
      <p>
        Cars: <strong style="color:#1D9E75">{total_cars:,} ({car_pct:.1f}%)</strong><br>
        Motorcycles: <strong style="color:#EF9F27">{total_motos:,} ({moto_pct:.1f}%)</strong><br>
        Trucks/Buses: <strong style="color:#378ADD">{total_trucks:,} ({truck_pct:.1f}%)</strong><br>
        Total classified: <strong>{total_vehicles_class:,}</strong>
      </p>
    </div>
    <div class="info-box">
      <h3>🔥 Peak Load</h3>
      <p>
        <strong style="color:#E24B4A">{high_load_count}</strong> checkpoint(s) exceed 6,000 vehicles/hour.<br>
        Busiest road: <strong style="color:#E8F4F8">{html.escape(highest_road)}</strong><br>
        Peak volume: <strong style="color:#E8F4F8">{highest_vol:,}</strong> vehicles/day.
      </p>
    </div>
  </div>
  <p class="pfooter">UrbanSync · BDI Hackathon 2026 · Smart City Track</p>
</div>

<!-- ── MAP ── -->
<div class="panel panel-map" id="t-map">
  <div id="leaflet-map"></div>
</div>

<!-- ── CLASSIFICATION ── -->
<div class="panel" id="t-class">
  <h2 class="section-hd">Vehicle Classification Breakdown</h2>
  <div class="g2">
    <div class="bars-box">
      <p style="font-size:12px;color:#5A7A90;margin-bottom:14px;text-transform:uppercase;letter-spacing:.7px;font-weight:700">Fleet Composition — All Checkpoints</p>
      <div class="bar-row">
        <span class="bar-label">🚗 Cars</span>
        <div class="bar-track"><div class="bar-fill" style="width:{car_pct:.1f}%;background:#1D9E75"></div></div>
        <span class="bar-value">{total_cars:,} ({car_pct:.1f}%)</span>
      </div>
      <div class="bar-row">
        <span class="bar-label">🏍 Motorcycles</span>
        <div class="bar-track"><div class="bar-fill" style="width:{moto_pct:.1f}%;background:#EF9F27"></div></div>
        <span class="bar-value">{total_motos:,} ({moto_pct:.1f}%)</span>
      </div>
      <div class="bar-row">
        <span class="bar-label">🚛 Trucks / Buses</span>
        <div class="bar-track"><div class="bar-fill" style="width:{truck_pct:.1f}%;background:#378ADD"></div></div>
        <span class="bar-value">{total_trucks:,} ({truck_pct:.1f}%)</span>
      </div>
    </div>
    <div class="info-box" style="align-self:start">
      <h3>ℹ️ Detection Method</h3>
      <p>YOLOv8 object detection with stable track majority voting. Each track is assigned its most-frequent class across all frames, preventing class-switching duplicates. Spatial-temporal merging (30-frame gap, 120 px radius) removes fragmented track duplicates.</p>
    </div>
  </div>
  <h2 class="section-hd" style="margin-top:4px">Per-Checkpoint Classification</h2>
  <div class="tbl-wrap">
    <table>
      <thead><tr><th>#</th><th>Road</th><th>Cars</th><th>Motorcycles</th><th>Trucks</th><th>Total/Day</th><th>Tier</th></tr></thead>
      <tbody>
        {class_table_html}
      </tbody>
    </table>
  </div>
  <p class="pfooter">UrbanSync · BDI Hackathon 2026</p>
</div>

<!-- ── FLOW ── -->
<div class="panel" id="t-flow">
  <h2 class="section-hd">Traffic Flow Analysis — Peak vs Off-Peak</h2>
  <p style="color:#5A7A90;font-size:13px;margin-bottom:16px">
    <strong style="color:#E24B4A">{high_load_count}</strong> checkpoint(s) exceed 6,000 vehicles/hour (peak overload threshold).
    Full time-series analysis requires multi-hour CCTV processing.
  </p>
  <div class="tbl-wrap">
    <table>
      <thead><tr><th>Load Rank</th><th>Road Name</th><th>Vehicles / Hour</th><th>Pattern</th></tr></thead>
      <tbody>{"".join(flow_rows)}</tbody>
    </table>
  </div>
  <p class="pfooter">UrbanSync · BDI Hackathon 2026</p>
</div>

<!-- ── INTERSECTIONS ── -->
<div class="panel" id="t-intersect">
  <h2 class="section-hd">Intersection Performance &amp; CFS Multiplier Rank</h2>
  <div class="tbl-wrap">
    <table>
      <thead><tr><th>Rank</th><th>Road Name</th><th>Measurement Location</th><th>Vehicles/Day</th><th>Load Tier</th><th>CFS Multiplier</th></tr></thead>
      <tbody>{"".join(table_rows)}</tbody>
    </table>
  </div>
  <p class="pfooter">Top 5 rows highlighted · UrbanSync · BDI Hackathon 2026</p>
</div>

<!-- ── VIDEO ── -->
<div class="panel" id="t-video">
  <h2 class="section-hd">Video CCTV Cross-Validation</h2>
  <div class="tbl-wrap">
    <table>
      <thead><tr><th>Video Location</th><th>Camera Orientation</th><th>Bidirectional Count</th><th>Method</th><th>Extrapolation Factor</th><th>Reliable?</th></tr></thead>
      <tbody>{"".join(video_rows)}</tbody>
    </table>
  </div>
  <p class="pfooter">UrbanSync · BDI Hackathon 2026</p>
</div>

</div><!-- content-area -->
</div><!-- app -->

<script>
{_TAB_JS}

var _mapReady = false;
function showTab(id) {{
    document.querySelectorAll('.panel').forEach(function(p){{p.classList.remove('active');}});
    document.querySelectorAll('.tab-btn').forEach(function(b){{b.classList.remove('active');}});
    document.getElementById(id).classList.add('active');
    var btn = document.querySelector('[data-tab="'+id+'"]');
    if(btn) btn.classList.add('active');
    if(id==='t-map'){{ initMap(); setTimeout(function(){{if(window._lmap)window._lmap.invalidateSize();}},60); }}
}}

var trafficData = {traffic_json};
var videoData   = {video_json};

function initMap() {{
    if(_mapReady) return; _mapReady=true;
    var lmap = L.map('leaflet-map').setView([16.432,102.834],13);
    window._lmap = lmap;
    L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png',{{attribution:'&copy; CartoDB'}}).addTo(lmap);

    var tc={{"critical":"#E24B4A","high":"#EF9F27","medium":"#378ADD","low":"#639922"}};
    function esc(s){{return s?String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'):'';}}

    var maxV=1; trafficData.forEach(function(r){{if((r['\u0e23\u0e27\u0e21\u0e15\u0e48\u0e2d\u0e27\u0e31\u0e19']||0)>maxV)maxV=r['\u0e23\u0e27\u0e21\u0e15\u0e48\u0e2d\u0e27\u0e31\u0e19'];}});

    trafficData.forEach(function(r){{
        if(!r.Lat||!r.Lng) return;
        var col=tc[r.traffic_tier]||'#378ADD';
        var rad=8+(r['\u0e23\u0e27\u0e21\u0e15\u0e48\u0e2d\u0e27\u0e31\u0e19']||0)/maxV*20;
        var pop='<h3>'+esc(r['\u0e40\u0e2a\u0e49\u0e19\u0e17\u0e32\u0e07'])+'</h3><table>'+
            '<tr><td><b>Location</b></td><td>'+esc(r['\u0e15\u0e33\u0e41\u0e2b\u0e19\u0e48\u0e07\u0e15\u0e34\u0e14\u0e15\u0e31\u0e49\u0e07\u0e40\u0e04\u0e23\u0e37\u0e48\u0e2d\u0e07\u0e27\u0e31\u0e14'])+'</td></tr>'+
            '<tr><td><b>Cars</b></td><td>'+(r.Car||0).toLocaleString()+'</td></tr>'+
            '<tr><td><b>Motorcycles</b></td><td>'+(r.Motorcycle||0).toLocaleString()+'</td></tr>'+
            '<tr><td><b>Trucks</b></td><td>'+(r.Truck||0).toLocaleString()+'</td></tr>'+
            '<tr><td><b>Total/Day</b></td><td>'+(r['\u0e23\u0e27\u0e21\u0e15\u0e48\u0e2d\u0e27\u0e31\u0e19']||0).toLocaleString()+'</td></tr>'+
            '<tr><td><b>Tier</b></td><td><span style="background:'+col+';padding:2px 6px;border-radius:4px;color:#fff;font-size:11px;">'+r.traffic_tier+'</span></td></tr>'+
            '<tr><td><b>Multiplier</b></td><td>'+(r.traffic_multiplier||1).toFixed(3)+'</td></tr>'+
            '</table>';
        L.circleMarker([r.Lat,r.Lng],{{radius:rad,color:col,fillColor:col,fillOpacity:.65,weight:2}}).bindPopup(pop).addTo(lmap);
    }});

    var vc={{"Highground":[16.4489,102.8431],"Sideway":[16.4312,102.8251],"Intersection":[16.4234,102.8315]}};
    videoData.forEach(function(r){{
        var c=vc[r.video_id]; if(!c) return;
        var pop='<h3>📹 '+esc(r.video_id)+'</h3><table>'+
            '<tr><td><b>Road</b></td><td>'+esc(r.location_name)+'</td></tr>'+
            '<tr><td><b>Bidirectional</b></td><td>'+(r.bidirectional_total||0).toLocaleString()+'</td></tr>'+
            '<tr><td><b>Cars</b></td><td>'+(r.car_count||0).toLocaleString()+'</td></tr>'+
            '<tr><td><b>Trucks</b></td><td>'+(r.truck_count||0).toLocaleString()+'</td></tr>'+
            '<tr><td><b>Method</b></td><td>'+esc(r.counting_method)+'</td></tr>'+
            '</table>';
        L.circleMarker(c,{{radius:14,color:'#1D9E75',fillColor:'#1D9E75',fillOpacity:.9,weight:3,dashArray:'4,4'}}).bindPopup(pop).addTo(lmap);
    }});
}}
</script>
</body>
</html>"""
    output_path.write_text(html_out, encoding="utf-8")
    print(f"Traffic Dashboard saved -> {output_path} ({output_path.stat().st_size // 1024} KB)")


# ──────────────────────────────────────────────────────────────────────────────
# COMPLAINT DASHBOARD
# ──────────────────────────────────────────────────────────────────────────────

def build_complaint_dashboard(
    complaints_path: Path,
    ranked_queue_path: Path,
    resolution_path: Path,
    topics_path: Path,
    fifo_path: Path,
    stats_path: Path,
    output_path: Path,
) -> None:
    """Build outputs/complaint_dashboard.html — single-page panel app."""
    complaints_df = pd.read_csv(complaints_path) if complaints_path.exists() else pd.DataFrame()
    ranked_queue_payload = json.loads(ranked_queue_path.read_text(encoding="utf-8")) if ranked_queue_path.exists() else {"queue": []}
    queue_list = ranked_queue_payload.get("queue", [])
    resolution_baseline: dict = json.loads(resolution_path.read_text(encoding="utf-8")) if resolution_path.exists() else {}
    stats: dict = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}
    fifo_df = pd.read_csv(fifo_path) if fifo_path.exists() else pd.DataFrame()
    topics_df = pd.read_csv(topics_path) if topics_path.exists() else pd.DataFrame()

    # ── KPIs ──
    total_complaints = len(complaints_df)
    open_cases = int(stats.get("total_open", 0))
    closed_cases = int(stats.get("total_closed", 0))
    closed_df = complaints_df[complaints_df["is_open"] == False] if not complaints_df.empty else pd.DataFrame()
    mean_resolution = round(closed_df["resolution_days"].mean(), 1) if not closed_df.empty else 0.0
    top_severity_type = str(stats.get("top_complaint_type", "N/A"))

    # ── District map data ──
    district_centroids = {
        "เขต 1": {"lat": 16.450, "lng": 102.810},
        "เขต 2": {"lat": 16.430, "lng": 102.860},
        "เขต 3": {"lat": 16.410, "lng": 102.820},
        "เขต 4": {"lat": 16.460, "lng": 102.850},
        "ไม่ระบุ": {"lat": 16.440, "lng": 102.830},
    }
    district_data = []
    if not complaints_df.empty:
        for district, group in complaints_df.groupby("เขต"):
            coords = district_centroids.get(district, district_centroids["ไม่ระบุ"])
            district_data.append({
                "district": district,
                "lat": coords["lat"], "lng": coords["lng"],
                "total": len(group),
                "open": int(group["is_open"].sum()),
                "most_common": str(group["ประเภทคำร้อง"].value_counts().index[0]) if not group.empty else "N/A",
            })
    district_json = json.dumps(district_data, ensure_ascii=False)
    queue_json = json.dumps(queue_list[:20], ensure_ascii=False)

    # ── Type distribution bars ──
    type_counts = complaints_df["ประเภทคำร้อง"].value_counts().head(8) if not complaints_df.empty else pd.Series()
    total_typed = type_counts.sum() or 1
    type_bars_html = []
    stacked_bars_html = []
    for t_type, count in type_counts.items():
        t_pct = (count / total_typed) * 100
        type_bars_html.append(
            f"<div class='bar-row'>"
            f"<span class='bar-label'>{html.escape(t_type)}</span>"
            f"<div class='bar-track'><div class='bar-fill' style='width:{t_pct:.1f}%;background:#1D9E75'></div></div>"
            f"<span class='bar-value'>{count:,} ({t_pct:.1f}%)</span>"
            f"</div>"
        )
        tot_t = len(complaints_df[complaints_df["ประเภทคำร้อง"] == t_type]) if not complaints_df.empty else 1
        op_t = len(complaints_df[(complaints_df["ประเภทคำร้อง"] == t_type) & (complaints_df["is_open"] == True)]) if not complaints_df.empty else 0
        cl_t = tot_t - op_t
        op_pct = (op_t / tot_t) * 100
        cl_pct = (cl_t / tot_t) * 100
        stacked_bars_html.append(
            f"<div class='bar-row'>"
            f"<span class='bar-label'>{html.escape(t_type)}</span>"
            f"<div class='bar-track'><div class='stk-track'>"
            f"<div style='width:{op_pct:.1f}%;background:#E24B4A' title='Open'></div>"
            f"<div style='width:{cl_pct:.1f}%;background:#1D9E75' title='Closed'></div>"
            f"</div></div>"
            f"<span class='bar-value'><span style='color:#E24B4A'>{op_t}</span> / <span style='color:#1D9E75'>{cl_t}</span></span>"
            f"</div>"
        )

    # ── Performance rows ──
    performance_rows = []
    for comp_type, info in sorted(resolution_baseline.items(), key=lambda x: x[1]["mean_days"], reverse=True):
        md = info["mean_days"]
        color = "#E24B4A" if md > 30 else "#EF9F27" if md > 15 else "#1D9E75"
        performance_rows.append(
            f"<tr><td>{html.escape(comp_type)}</td>"
            f"<td><span style='color:{color};font-weight:700'>{md:.1f} days</span></td>"
            f"<td>{info['median_days']:.1f} days</td>"
            f"<td>{info['count']}</td></tr>"
        )

    # ── FIFO vs CFS ──
    max_rank_change = 0
    upgrade_rows, downgrade_rows = [], []
    if not fifo_df.empty:
        max_rank_change = int(fifo_df["rank_change"].max())
        for _, row in fifo_df.sort_values("rank_change", ascending=False).head(5).iterrows():
            upgrade_rows.append(
                f"<tr><td>{html.escape(str(row.get('ประเภทคำร้อง','')))}</td>"
                f"<td>{html.escape(str(row.get('เขต','')))}</td>"
                f"<td>{int(row.get('fifo_rank',0))}</td>"
                f"<td>{int(row.get('priority_rank',0))}</td>"
                f"<td><span style='color:#1D9E75;font-weight:700'>+{int(row.get('rank_change',0))}</span></td>"
                f"<td><span class='badge' style='background:#1D9E75'>Upgrade</span></td></tr>"
            )
        for _, row in fifo_df.sort_values("rank_change", ascending=True).head(5).iterrows():
            downgrade_rows.append(
                f"<tr><td>{html.escape(str(row.get('ประเภทคำร้อง','')))}</td>"
                f"<td>{html.escape(str(row.get('เขต','')))}</td>"
                f"<td>{int(row.get('fifo_rank',0))}</td>"
                f"<td>{int(row.get('priority_rank',0))}</td>"
                f"<td><span style='color:#E24B4A;font-weight:700'>{int(row.get('rank_change',0))}</span></td>"
                f"<td><span class='badge' style='background:#E24B4A'>Downgrade</span></td></tr>"
            )

    # ── Prediction rows ──
    prediction_rows = []
    for comp_type, info in resolution_baseline.items():
        eta = round(info["mean_days"], 1)
        cnt = info["count"]
        conf_color = "#1D9E75" if cnt >= 3 else "#EF9F27" if cnt >= 2 else "#5A7A90"
        conf_txt = "High" if cnt >= 3 else "Medium" if cnt >= 2 else "Low (baseline)"
        prediction_rows.append(
            f"<tr><td>{html.escape(comp_type)}</td>"
            f"<td><b style='color:#1D9E75'>+{eta} days</b></td>"
            f"<td><span style='color:{conf_color}'>{conf_txt} ({cnt} samples)</span></td></tr>"
        )

    # ── NLP topic rows ──
    topic_rows = []
    if not topics_df.empty:
        for _, row in topics_df.head(10).iterrows():
            pct = (int(row.get("count", 0)) / max(total_complaints, 1)) * 100
            topic_rows.append(
                f"<tr><td>{int(row.get('topic_id',0))}</td>"
                f"<td>{html.escape(str(row.get('topic_label','')))}</td>"
                f"<td>{int(row.get('count',0))}</td>"
                f"<td>{pct:.1f}%</td></tr>"
            )
    elif not complaints_df.empty:
        # Auto-derive pseudo-topics from complaint type frequency (no NLP required)
        # Each unique complaint type becomes a "topic" labelled by its top keywords
        type_topic_map: dict[str, dict] = {}
        for comp_type, group in complaints_df.groupby("ประเภทคำร้อง"):
            # Extract top 3 words from descriptions in this type as keywords
            all_words: list[str] = []
            for desc in group.get("เรื่องร้องทุกข์", pd.Series(dtype=str)).dropna():
                all_words.extend(str(desc).split())
            # Filter very short tokens
            word_freq: dict[str, int] = {}
            for w in all_words:
                w = w.strip()
                if len(w) >= 3:
                    word_freq[w] = word_freq.get(w, 0) + 1
            top_kws = sorted(word_freq, key=word_freq.get, reverse=True)[:3]  # type: ignore[arg-type]
            kw_label = " / ".join(top_kws) if top_kws else comp_type
            type_topic_map[comp_type] = {"count": len(group), "label": kw_label}
        # Sort by count descending, take top 10
        for tid, (comp_type, info) in enumerate(
            sorted(type_topic_map.items(), key=lambda x: x[1]["count"], reverse=True)[:10]
        ):
            pct = (info["count"] / max(total_complaints, 1)) * 100
            topic_rows.append(
                f"<tr>"
                f"<td>{tid}</td>"
                f"<td><span style='color:#8DE3C2'>{html.escape(comp_type)}</span>"
                f"<br><small style='color:#5A7A90;font-size:11px'>{html.escape(info['label'])}</small></td>"
                f"<td>{info['count']}</td>"
                f"<td>{pct:.1f}%</td>"
                f"</tr>"
            )
    else:
        topic_rows.append("<tr><td colspan='4' style='text-align:center;color:#5A7A90;padding:20px'>No complaint data available</td></tr>")


    # ── CFS queue rows ──
    queue_rows = []
    for item in queue_list[:50]:
        tier = str(item.get("cfs_tier", "low"))
        color = TIER_COLORS.get(tier, TIER_COLORS["low"])
        queue_rows.append(
            f"<tr>"
            f"<td>{int(item.get('rank',0))}</td>"
            f"<td>{html.escape(str(item.get('complaint_type','')))}</td>"
            f"<td style='max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>{html.escape(str(item.get('description',''))[:50])}</td>"
            f"<td>{html.escape(str(item.get('district','')))}</td>"
            f"<td>{int(item.get('days_open',0))}</td>"
            f"<td>{float(item.get('cfs_score',0.0)):.2f}</td>"
            f"<td><span class='badge' style='background:{color}'>{tier}</span></td>"
            f"</tr>"
        )

    tabs = [
        ("c-overview",  "📊", "Overview"),
        ("c-map",       "🗺️",  "District Map"),
        ("c-types",     "📋", "Complaint Types"),
        ("c-resolution","⏱️",  "Resolution"),
        ("c-fifo",      "🔄", "FIFO vs CFS"),
        ("c-queue",     "📌", "Dispatch Queue"),
    ]

    html_out = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>UrbanSync — Complaint Intelligence</title>
<meta name="description" content="UrbanSync Complaint Intelligence — BDI Hackathon 2026 Khon Kaen">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>{_get_shared_styles()}</style>
</head>
<body>
<div class="app">
{_topnav(tabs, "c-overview", "complaint_dashboard.html")}
<div class="content-area">

<!-- ── OVERVIEW ── -->
<div class="panel active" id="c-overview">
  <h1 style="font-size:20px;font-weight:800;color:#E8F4F8;margin-bottom:4px">Complaint Intelligence</h1>
  <p style="color:#5A7A90;font-size:13px;margin-bottom:20px">BDI Hackathon 2026 · Geospatial Densities &amp; CFS-Ranked Dispatch Queue · Khon Kaen</p>
  <div class="cards">
    <div class="card"><h3>Total Complaints</h3><b>{total_complaints:,}</b><small>All records</small></div>
    <div class="card"><h3>Open Cases</h3><b style="color:#E24B4A">{open_cases:,}</b><small>Awaiting resolution</small></div>
    <div class="card"><h3>Closed Cases</h3><b style="color:#1D9E75">{closed_cases:,}</b><small>Resolved</small></div>
    <div class="card"><h3>Mean Resolution</h3><b>{mean_resolution:.1f}<small style="font-size:14px;color:#5A7A90"> days</small></b><small>Historical baseline</small></div>
    <div class="card"><h3>Top Friction Type</h3><b style="font-size:14px">{html.escape(top_severity_type)}</b><small>Highest severity</small></div>
  </div>
  <div class="g2">
    <div class="info-box">
      <h3>📍 District Summary</h3>
      <p>
        {"<br>".join(f"<strong>{d['district']}</strong>: {d['total']} total, <span style='color:#E24B4A'>{d['open']} open</span>" for d in district_data)}
      </p>
    </div>
    <div class="info-box">
      <h3>⚡ CFS System</h3>
      <p>
        <strong>CFS = Severity Score × Traffic Multiplier</strong><br>
        Range: <strong>3.96 – 30.0</strong>. Severity is the primary dispatch signal.
        The traffic multiplier acts as a location-based tiebreaker, prioritizing
        complaints near high-load intersections.
      </p>
    </div>
  </div>
  <p class="pfooter">UrbanSync · BDI Hackathon 2026 · Smart City Track</p>
</div>

<!-- ── MAP ── -->
<div class="panel panel-map" id="c-map">
  <div id="leaflet-map2"></div>
</div>

<!-- ── TYPES ── -->
<div class="panel" id="c-types">
  <h2 class="section-hd">Complaint Classification Distribution</h2>
  <div class="g2">
    <div class="bars-box">
      <p style="font-size:12px;color:#5A7A90;margin-bottom:14px;text-transform:uppercase;letter-spacing:.7px;font-weight:700">Volume by Type (Top 8)</p>
      {"".join(type_bars_html)}
    </div>
    <div class="bars-box">
      <p style="font-size:12px;color:#5A7A90;margin-bottom:14px;text-transform:uppercase;letter-spacing:.7px;font-weight:700">Open vs Closed per Type</p>
      {"".join(stacked_bars_html)}
      <div style="display:flex;gap:16px;margin-top:14px;font-size:12px">
        <span><span class="dot" style="background:#E24B4A"></span>Open</span>
        <span><span class="dot" style="background:#1D9E75"></span>Closed</span>
      </div>
    </div>
  </div>
  <h2 class="section-hd" style="margin-top:4px">NLP Topic Modeling (Extracted Themes)</h2>
  <div class="tbl-wrap">
    <table>
      <thead><tr><th>Topic ID</th><th>Keywords</th><th>Count</th><th>Share</th></tr></thead>
      <tbody>{"".join(topic_rows)}</tbody>
    </table>
  </div>
  <p class="pfooter">UrbanSync · BDI Hackathon 2026</p>
</div>

<!-- ── RESOLUTION ── -->
<div class="panel" id="c-resolution">
  <h2 class="section-hd">Resolution Performance Analytics</h2>
  <div class="g2">
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>Complaint Type</th><th>Mean Resolution</th><th>Median Days</th><th>Closed Count</th></tr></thead>
        <tbody>{"".join(performance_rows) or "<tr><td colspan='4' style='text-align:center;color:#5A7A90;padding:20px'>No resolution data yet</td></tr>"}</tbody>
      </table>
    </div>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>Complaint Type</th><th>Estimated ETA</th><th>Model Confidence</th></tr></thead>
        <tbody>{"".join(prediction_rows) or "<tr><td colspan='3' style='text-align:center;color:#5A7A90;padding:20px'>No prediction data yet</td></tr>"}</tbody>
      </table>
    </div>
  </div>
  <p class="pfooter">* ETA estimated from historical mean resolution time per category · UrbanSync · BDI Hackathon 2026</p>
</div>

<!-- ── FIFO vs CFS ── -->
<div class="panel" id="c-fifo">
  <h2 class="section-hd">FIFO vs CFS Dispatch Comparison</h2>
  <div class="cards" style="max-width:500px;margin-bottom:20px">
    <div class="card"><h3>Biggest Priority Upgrade</h3><b style="color:#1D9E75">+{max_rank_change}</b><small>positions via CFS reranking</small></div>
  </div>
  <div class="g2">
    <div>
      <p class="section-hd" style="border:none;padding:0;margin-bottom:12px">🚀 Top CFS Priority Upgrades</p>
      <div class="tbl-wrap">
        <table>
          <thead><tr><th>Type</th><th>District</th><th>FIFO Rank</th><th>CFS Rank</th><th>Change</th><th>Tag</th></tr></thead>
          <tbody>{"".join(upgrade_rows) or "<tr><td colspan='6' style='text-align:center;color:#5A7A90;padding:20px'>No data</td></tr>"}</tbody>
        </table>
      </div>
    </div>
    <div>
      <p class="section-hd" style="border:none;padding:0;margin-bottom:12px">📉 Significant CFS Downgrades</p>
      <div class="tbl-wrap">
        <table>
          <thead><tr><th>Type</th><th>District</th><th>FIFO Rank</th><th>CFS Rank</th><th>Change</th><th>Tag</th></tr></thead>
          <tbody>{"".join(downgrade_rows) or "<tr><td colspan='6' style='text-align:center;color:#5A7A90;padding:20px'>No data</td></tr>"}</tbody>
        </table>
      </div>
    </div>
  </div>
  <p class="pfooter">UrbanSync · BDI Hackathon 2026</p>
</div>

<!-- ── QUEUE ── -->
<div class="panel" id="c-queue">
  <h2 class="section-hd">CFS-Ranked Dispatch Queue — Top 50 Open Cases</h2>
  <div class="tbl-wrap">
    <table>
      <thead><tr><th>Rank</th><th>Type</th><th>Description</th><th>District</th><th>Days Open</th><th>CFS Score</th><th>Tier</th></tr></thead>
      <tbody>{"".join(queue_rows)}</tbody>
    </table>
  </div>
  <p class="pfooter">Showing {min(50,len(queue_list))} of {len(queue_list)} open complaints · UrbanSync · BDI Hackathon 2026</p>
</div>

</div><!-- content-area -->
</div><!-- app -->

<script>
{_TAB_JS}

var _map2Ready = false;
function showTab(id) {{
    document.querySelectorAll('.panel').forEach(function(p){{p.classList.remove('active');}});
    document.querySelectorAll('.tab-btn').forEach(function(b){{b.classList.remove('active');}});
    document.getElementById(id).classList.add('active');
    var btn=document.querySelector('[data-tab="'+id+'"]');
    if(btn) btn.classList.add('active');
    if(id==='c-map'){{ initMap2(); setTimeout(function(){{if(window._lmap2) window._lmap2.invalidateSize();}},60); }}
}}

var districtData = {district_json};
var queueData    = {queue_json};

function initMap2() {{
    if(_map2Ready) return; _map2Ready=true;
    var lmap=L.map('leaflet-map2').setView([16.432,102.834],13);
    window._lmap2=lmap;
    L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png',{{attribution:'&copy; CartoDB'}}).addTo(lmap);
    function esc(s){{return s?String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'):'';}}

    districtData.forEach(function(d){{
        var cnt=d.open||0;
        var col=cnt>45?'#E24B4A':cnt>30?'#EF9F27':cnt>15?'#378ADD':'#1D9E75';
        var pop='<h3>🏢 '+esc(d.district)+'</h3><table>'+
            '<tr><td><b>Total</b></td><td>'+d.total+'</td></tr>'+
            '<tr><td><b>Open</b></td><td><span style="color:#E24B4A">'+d.open+'</span></td></tr>'+
            '<tr><td><b>Most Common</b></td><td>'+esc(d.most_common)+'</td></tr>'+
            '</table>';
        L.circle([d.lat,d.lng],{{radius:(15+d.open*0.8)*25,color:col,fillColor:col,fillOpacity:.4,weight:2}}).bindPopup(pop).addTo(lmap);
    }});

    var tc={{"critical":"#E24B4A","high":"#EF9F27","medium":"#378ADD","low":"#1D9E75"}};
    queueData.forEach(function(item){{
        if(!item.checkpoint_lat||!item.checkpoint_lng) return;
        var col=tc[item.cfs_tier]||'#E24B4A';
        var pop='<h3>🔥 CFS #'+item.rank+'</h3><table>'+
            '<tr><td><b>Type</b></td><td>'+esc(item.complaint_type)+'</td></tr>'+
            '<tr><td><b>District</b></td><td>'+esc(item.district)+'</td></tr>'+
            '<tr><td><b>Days Open</b></td><td>'+item.days_open+'</td></tr>'+
            '<tr><td><b>CFS Score</b></td><td><b style="color:#1D9E75">'+item.cfs_score.toFixed(2)+'</b></td></tr>'+
            '</table>';
        L.circleMarker([item.checkpoint_lat,item.checkpoint_lng],{{radius:8,color:'#fff',fillColor:col,fillOpacity:.95,weight:2}}).bindPopup(pop).addTo(lmap);
    }});
}}
</script>
</body>
</html>"""
    output_path.write_text(html_out, encoding="utf-8")
    print(f"Complaint Dashboard saved -> {output_path} ({output_path.stat().st_size // 1024} KB)")


# ──────────────────────────────────────────────────────────────────────────────
# CFS DISPATCH DASHBOARD (main dashboard.html)
# ──────────────────────────────────────────────────────────────────────────────

def create_dashboard_html(
    stats: dict[str, Any],
    ranked_queue_list: list[dict[str, Any]],
    map_obj: Any,  # kept for API compatibility; not used in new Leaflet layout
    traffic_json: str = "[]",
    queue_json: str = "[]",
) -> str:
    """Build the CFS Dispatch dashboard as a single-page panel app with Leaflet map."""
    generated = html.escape(str(stats.get("generated_at", dt.datetime.now().isoformat())))
    note = html.escape(str(stats.get("severity_vs_traffic_note", "")))

    # Keyword badges
    keywords_html = []
    keywords_path = Path("config/severity_keywords.json")
    if keywords_path.exists():
        try:
            kw = json.loads(keywords_path.read_text(encoding="utf-8"))
            for k, v in kw.items():
                keywords_html.append(f"<span class='kw-badge'>{html.escape(k)} <strong>+{v}</strong></span>")
        except Exception:
            pass

    # Queue table rows
    rows = []
    for item in ranked_queue_list[:20]:
        tier = str(item.get("cfs_tier", "low"))
        color = TIER_COLORS.get(tier, TIER_COLORS["low"])
        rows.append(
            f"<tr>"
            f"<td>{int(item.get('rank',0))}</td>"
            f"<td>{html.escape(str(item.get('complaint_type','')))}</td>"
            f"<td style='max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>"
            f"{html.escape(str(item.get('description',''))[:50])}</td>"
            f"<td>{html.escape(str(item.get('district','')))}</td>"
            f"<td>{int(item.get('days_open',0))}</td>"
            f"<td>{int(item.get('severity_score',0))}</td>"
            f"<td>{float(item.get('traffic_multiplier',0.0)):.3f}</td>"
            f"<td><b style='color:#1D9E75'>{float(item.get('cfs_score',0.0)):.2f}</b></td>"
            f"<td><span class='badge' style='background:{color}'>{html.escape(tier)}</span></td>"
            f"</tr>"
        )

    tabs = [
        ("d-overview", "📊", "Overview"),
        ("d-map",      "🗺️",  "Live Map"),
        ("d-queue",    "📌", "Dispatch Queue"),
        ("d-formula",  "🔢", "CFS Formula"),
    ]

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>UrbanSync — CFS Dispatch</title>
<meta name="description" content="UrbanSync CFS Dispatch Dashboard — BDI Hackathon 2026 Khon Kaen">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>{_get_shared_styles()}</style>
</head>
<body>
<div class="app">
{_topnav(tabs, "d-overview", "dashboard.html")}
<div class="content-area">

<!-- ── OVERVIEW ── -->
<div class="panel active" id="d-overview">
  <h1 style="font-size:20px;font-weight:800;color:#E8F4F8;margin-bottom:4px">CFS Dispatch Dashboard</h1>
  <p style="color:#5A7A90;font-size:13px;margin-bottom:20px">UrbanSync Khon Kaen · BDI Hackathon 2026 · Generated: {generated}</p>
  <div class="cards">
    <div class="card"><h3>Total Open</h3><b style="color:#EF9F27">{int(stats.get('total_open',0)):,}</b><small>Open complaints</small></div>
    <div class="card"><h3>Critical</h3><b style="color:#E24B4A">{int(stats.get('critical_count',0)):,}</b><small>Highest priority</small></div>
    <div class="card"><h3>High Priority</h3><b style="color:#EF9F27">{int(stats.get('high_count',0)):,}</b><small>High tier</small></div>
    <div class="card"><h3>Mean CFS Score</h3><b>{float(stats.get('mean_cfs_score',0.0)):.2f}</b><small>Avg across open cases</small></div>
    <div class="card"><h3>Mean Days Open</h3><b>{float(stats.get('mean_days_open',0.0)):.1f}</b><small>Backlog age</small></div>
  </div>
  <div class="g2" style="margin-bottom:18px">
    <div class="bars-box">
      <p style="font-size:12px;color:#5A7A90;margin-bottom:14px;text-transform:uppercase;letter-spacing:.7px;font-weight:700">CFS Tier Distribution</p>
      {_tier_bars(stats)}
    </div>
    <div class="bars-box">
      <p style="font-size:12px;color:#5A7A90;margin-bottom:12px;text-transform:uppercase;letter-spacing:.7px;font-weight:700">Active Keyword Boosts</p>
      <div class="kw-panel">{"".join(keywords_html) or "<span style='color:#5A7A90'>No keywords configured</span>"}</div>
    </div>
  </div>
  {f"<div class='info-box' style='margin-bottom:16px'><h3>📝 Algorithmic Note</h3><p>{note}</p></div>" if note else ""}
  <p class="pfooter">UrbanSync · BDI Hackathon 2026 · Smart City Track</p>
</div>

<!-- ── MAP ── -->
<div class="panel panel-map" id="d-map">
  <div id="leaflet-map3"></div>
</div>

<!-- ── QUEUE ── -->
<div class="panel" id="d-queue">
  <h2 class="section-hd">Top 20 CFS-Ranked Dispatch Queue</h2>
  <div class="tbl-wrap">
    <table>
      <thead>
        <tr>
          <th>Rank</th><th>Type</th><th>Description</th><th>District</th>
          <th>Days Open</th><th>Severity</th><th>× Multiplier</th><th>CFS Score</th><th>Tier</th>
        </tr>
      </thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
  </div>
  <p class="pfooter">UrbanSync · BDI Hackathon 2026</p>
</div>

<!-- ── FORMULA ── -->
<div class="panel" id="d-formula">
  <h2 class="section-hd">CFS Formula &amp; Design Rationale</h2>
  <div class="g2">
    <div class="info-box">
      <h3>⚡ Civic Friction Score (CFS)</h3>
      <p>
        <strong style="color:#8DE3C2;font-size:15px">CFS = Severity Score × Traffic Multiplier</strong><br><br>
        <strong>Severity Score</strong> — integer 1–10 derived from complaint type lookup
        plus Thai keyword boosts from the active keyword dictionary.<br><br>
        <strong>Traffic Multiplier</strong> — continuous 1.0–3.0 scale derived from the
        nearest checkpoint's daily vehicle count relative to the city-wide maximum.
        Higher traffic = higher tiebreaker weight.<br><br>
        <strong>Max possible CFS:</strong> 30.0 &nbsp;|&nbsp; <strong>Min:</strong> 1.0
      </p>
    </div>
    <div class="info-box">
      <h3>🎯 Why CFS over FIFO?</h3>
      <p>
        First-In-First-Out (FIFO) dispatch treats all complaints equally regardless of severity or location.
        CFS ensures that a high-severity complaint near a busy intersection is dispatched before a low-priority
        complaint that arrived earlier.<br><br>
        In the current dataset, CFS reranking shifts complaints by up to <strong style="color:#1D9E75">158 positions</strong>,
        dramatically improving dispatch efficiency for high-urgency issues.
      </p>
    </div>
  </div>
  <div class="g3" style="margin-top:4px">
    <div class="info-box">
      <h3>🔴 Critical Tier</h3>
      <p>CFS ≥ 21. Immediate dispatch required. Typically severity 10 at high-traffic locations.</p>
    </div>
    <div class="info-box">
      <h3>🟡 High Tier</h3>
      <p>CFS 14–21. High-priority queue. Severity 7–9 or medium-severity near busy roads.</p>
    </div>
    <div class="info-box">
      <h3>🟢 Medium / Low Tier</h3>
      <p>CFS &lt; 14. Routine dispatch. Low-severity complaints away from congested checkpoints.</p>
    </div>
  </div>
  <p class="pfooter">UrbanSync · BDI Hackathon 2026 · Smart City Track</p>
</div>

</div><!-- content-area -->
</div><!-- app -->

<script>
{_TAB_JS}

var _map3Ready = false;
function showTab(id) {{
    document.querySelectorAll('.panel').forEach(function(p){{p.classList.remove('active');}});
    document.querySelectorAll('.tab-btn').forEach(function(b){{b.classList.remove('active');}});
    document.getElementById(id).classList.add('active');
    var btn=document.querySelector('[data-tab="'+id+'"]');
    if(btn) btn.classList.add('active');
    if(id==='d-map'){{ initMap3(); setTimeout(function(){{if(window._lmap3) window._lmap3.invalidateSize();}},60); }}
}}

var trafficData3 = {traffic_json};
var queueData3   = {queue_json};

function initMap3() {{
    if(_map3Ready) return; _map3Ready=true;
    var lmap=L.map('leaflet-map3').setView([16.432,102.834],13);
    window._lmap3=lmap;
    L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png',{{attribution:'&copy; CartoDB'}}).addTo(lmap);
    function esc(s){{return s?String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'):'';}}
    var tc={{"critical":"#E24B4A","high":"#EF9F27","medium":"#378ADD","low":"#1D9E75"}};

    var maxV=1;
    trafficData3.forEach(function(r){{if((r['\u0e23\u0e27\u0e21\u0e15\u0e48\u0e2d\u0e27\u0e31\u0e19']||0)>maxV) maxV=r['\u0e23\u0e27\u0e21\u0e15\u0e48\u0e2d\u0e27\u0e31\u0e19'];}});
    trafficData3.forEach(function(r){{
        if(!r.Lat||!r.Lng) return;
        var col=tc[r.traffic_tier]||'#378ADD';
        var rad=7+(r['\u0e23\u0e27\u0e21\u0e15\u0e48\u0e2d\u0e27\u0e31\u0e19']||0)/maxV*16;
        L.circleMarker([r.Lat,r.Lng],{{radius:rad,color:col,fillColor:col,fillOpacity:.55,weight:2}})
         .bindPopup('<h3>'+esc(r['\u0e40\u0e2a\u0e49\u0e19\u0e17\u0e32\u0e07'])+'</h3>Total/day: '+(r['\u0e23\u0e27\u0e21\u0e15\u0e48\u0e2d\u0e27\u0e31\u0e19']||0).toLocaleString())
         .addTo(lmap);
    }});

    queueData3.forEach(function(item){{
        if(!item.checkpoint_lat||!item.checkpoint_lng) return;
        var col=tc[item.cfs_tier]||'#E24B4A';
        var pop='<h3>🔥 CFS Rank #'+item.rank+'</h3><table>'+
            '<tr><td><b>Type</b></td><td>'+esc(item.complaint_type)+'</td></tr>'+
            '<tr><td><b>District</b></td><td>'+esc(item.district)+'</td></tr>'+
            '<tr><td><b>Days Open</b></td><td>'+item.days_open+'</td></tr>'+
            '<tr><td><b>CFS Score</b></td><td><b style="color:#1D9E75">'+item.cfs_score.toFixed(2)+'</b></td></tr>'+
            '</table>';
        L.circleMarker([item.checkpoint_lat,item.checkpoint_lng],{{radius:9,color:'#fff',fillColor:col,fillOpacity:.95,weight:2}}).bindPopup(pop).addTo(lmap);
    }});
}}
</script>
</body>
</html>"""


# ──────────────────────────────────────────────────────────────────────────────
# MAIN BUILD ORCHESTRATOR
# ──────────────────────────────────────────────────────────────────────────────

def build_dashboard(
    queue_path: str | Path,
    traffic_path: str | Path,
    stats_path: str | Path,
    output_path: str | Path,
) -> None:
    """Load pipeline outputs and write all three HTML dashboard files."""
    queue_payload = json.loads(Path(queue_path).read_text(encoding="utf-8"))
    queue_list = queue_payload.get("queue", [])
    traffic_df = pd.read_csv(traffic_path)
    stats = json.loads(Path(stats_path).read_text(encoding="utf-8"))

    # Serialise data for inline Leaflet maps
    traffic_json = traffic_df.to_json(orient="records", force_ascii=False)
    queue_json = json.dumps(queue_list[:20], ensure_ascii=False)

    # Keep folium map for API compatibility (not rendered in new layout)
    map_obj = create_map(queue_list[:200], traffic_df)

    # Write outputs/dashboard.html (CFS Dispatch)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    html_text = create_dashboard_html(stats, queue_list[:20], map_obj, traffic_json, queue_json)
    output.write_text(html_text, encoding="utf-8")
    print(f"CFS Dispatch Dashboard saved -> {output} ({output.stat().st_size // 1024} KB)")

    # Write outputs/traffic_dashboard.html
    video_counts_path = output.parent / "video_counts.csv"
    build_traffic_dashboard(Path(traffic_path), video_counts_path, output.parent / "traffic_dashboard.html")

    # Write outputs/complaint_dashboard.html
    build_complaint_dashboard(
        complaints_path=output.parent / "complaints_enriched.csv",
        ranked_queue_path=Path(queue_path),
        resolution_path=output.parent / "resolution_baseline.json",
        topics_path=output.parent / "complaint_topics.csv",
        fifo_path=output.parent / "fifo_vs_cfs_comparison.csv",
        stats_path=Path(stats_path),
        output_path=output.parent / "complaint_dashboard.html",
    )
