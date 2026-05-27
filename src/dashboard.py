# FILE: src/dashboard.py
"""Offline-friendly Folium dashboard generation."""

from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path
from typing import Any

import pandas as pd


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
    """Return HTML popup content for a traffic checkpoint."""
    return (
        f"<b>{html.escape(str(row.get('เส้นทาง', '')))}</b><br>"
        f"{html.escape(str(row.get('ตำแหน่งติดตั้งเครื่องวัด', '')))}<br>"
        f"Total/day: {int(row.get('รวมต่อวัน', 0)):,}<br>"
        f"Tier: {html.escape(str(row.get('traffic_tier', '')))}<br>"
        f"Multiplier: {float(row.get('traffic_multiplier', 1.0)):.1f}"
    )


def complaint_popup_html(complaint_dict: dict[str, Any]) -> str:
    """Return HTML popup content for a complaint marker."""
    return (
        f"<b>#{int(complaint_dict.get('rank', 0))} {html.escape(str(complaint_dict.get('complaint_type', '')))}</b><br>"
        f"{html.escape(str(complaint_dict.get('description', ''))[:120])}<br>"
        f"District: {html.escape(str(complaint_dict.get('district', '')))}<br>"
        f"Days open: {int(complaint_dict.get('days_open', 0))}<br>"
        f"CFS: {float(complaint_dict.get('cfs_score', 0.0)):.2f}"
    )


def create_map(ranked_queue_list: list[dict[str, Any]], traffic_df: pd.DataFrame) -> Any:
    """Create a Folium map with checkpoint, complaint, and top-priority layers."""
    folium = _require_folium()
    map_obj = folium.Map(location=KK_CENTER, zoom_start=13, tiles="OpenStreetMap")
    checkpoints = folium.FeatureGroup(name="Traffic checkpoints", show=True)
    max_volume = max(float(traffic_df["รวมต่อวัน"].max()), 1.0) if not traffic_df.empty else 1.0
    for _, row in traffic_df.iterrows():
        radius = 8 + int((float(row.get("รวมต่อวัน", 0)) / max_volume) * 16)
        folium.CircleMarker(
            location=[float(row["Lat"]), float(row["Lng"])],
            radius=radius,
            color="#185FA5",
            fill=True,
            fill_color="#378ADD",
            fill_opacity=0.6,
            popup=folium.Popup(html=checkpoint_popup_html(row), max_width=280),
        ).add_to(checkpoints)
    checkpoints.add_to(map_obj)
    complaints = folium.FeatureGroup(name="Open complaints", show=True)
    top_priority = folium.FeatureGroup(name="Top 20 priority", show=True)
    for complaint in ranked_queue_list:
        lat = complaint.get("checkpoint_lat")
        lng = complaint.get("checkpoint_lng")
        if lat is None or lng is None:
            continue
        color = TIER_COLORS.get(str(complaint.get("cfs_tier", "low")), TIER_COLORS["low"])
        popup = folium.Popup(html=complaint_popup_html(complaint), max_width=300)
        folium.CircleMarker(location=[lat, lng], radius=6, color=color, fill=True, fill_opacity=0.75, popup=popup).add_to(complaints)
        if int(complaint.get("rank", 999999)) <= 20:
            folium.Marker(location=[lat, lng], icon=folium.Icon(color="red", icon="exclamation-sign"), popup=popup).add_to(top_priority)
    complaints.add_to(map_obj)
    top_priority.add_to(map_obj)
    folium.LayerControl().add_to(map_obj)
    return map_obj


def _tier_bars(stats: dict[str, Any]) -> str:
    """Render simple tier distribution bars as HTML."""
    total = max(int(stats.get("total_open", 0)), 1)
    bars = []
    for tier in ["critical", "high", "medium", "low"]:
        count = int(stats.get(f"{tier}_count", 0))
        width = round((count / total) * 100, 1)
        bars.append(
            f"<div class='bar-row'><span>{tier.title()}</span><div class='bar-track'>"
            f"<div class='bar-fill' style='width:{width}%;background:{TIER_COLORS[tier]}'></div></div><b>{count}</b></div>"
        )
    return "\n".join(bars)


def create_dashboard_html(stats: dict[str, Any], ranked_queue_list: list[dict[str, Any]], map_obj: Any) -> str:
    """Build a complete standalone dashboard HTML document."""
    rows = []
    for item in ranked_queue_list:
        tier = str(item.get("cfs_tier", "low"))
        rows.append(
            "<tr>"
            f"<td>{int(item.get('rank', 0))}</td>"
            f"<td>{html.escape(str(item.get('complaint_type', '')))}</td>"
            f"<td>{html.escape(str(item.get('description', ''))[:40])}</td>"
            f"<td>{html.escape(str(item.get('district', '')))}</td>"
            f"<td>{int(item.get('days_open', 0))}</td>"
            f"<td>{int(item.get('severity_score', 0))}</td>"
            f"<td>{float(item.get('traffic_multiplier', 0.0)):.1f}</td>"
            f"<td>{float(item.get('cfs_score', 0.0)):.2f}</td>"
            f"<td><span class='badge' style='background:{TIER_COLORS.get(tier, TIER_COLORS['low'])}'>{html.escape(tier)}</span></td>"
            "</tr>"
        )
    generated = html.escape(str(stats.get("generated_at", dt.datetime.now().isoformat())))
    map_html = map_obj._repr_html_()
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UrbanSync Khon Kaen</title>
<style>
body {{ margin:0; background:#0D1B2A; color:#F5F7FA; font-family:Inter,Segoe UI,Arial,sans-serif; }}
header {{ padding:24px 32px; border-bottom:1px solid #1D9E75; }}
h1 {{ margin:0; font-size:32px; letter-spacing:0; }}
.subtitle {{ color:#9FB3C8; margin-top:6px; }}
main {{ padding:24px 32px 36px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; margin-bottom:22px; }}
.card {{ background:#12263A; border:1px solid #1E3A56; border-radius:8px; padding:16px; }}
.card b {{ display:block; color:#1D9E75; font-size:26px; margin-top:6px; }}
.map {{ height:500px; overflow:hidden; border-radius:8px; border:1px solid #1E3A56; background:#fff; margin-bottom:24px; }}
.map iframe, .map .folium-map {{ height:500px !important; width:100% !important; }}
table {{ width:100%; border-collapse:collapse; background:#12263A; border-radius:8px; overflow:hidden; }}
th,td {{ padding:10px 12px; border-bottom:1px solid #1E3A56; text-align:left; font-size:14px; }}
th {{ color:#8DE3C2; background:#0F2235; }}
.badge {{ color:#fff; border-radius:6px; padding:4px 8px; font-weight:700; }}
.bars {{ margin:24px 0; background:#12263A; border:1px solid #1E3A56; border-radius:8px; padding:16px; }}
.bar-row {{ display:grid; grid-template-columns:90px 1fr 50px; gap:12px; align-items:center; margin:10px 0; }}
.bar-track {{ height:12px; background:#0B1622; border-radius:99px; overflow:hidden; }}
.bar-fill {{ height:100%; }}
footer {{ color:#9FB3C8; padding:24px 32px; border-top:1px solid #1E3A56; }}
</style>
</head>
<body>
<header><h1>UrbanSync Khon Kaen</h1><div class="subtitle">CFS Dispatch Dashboard · {generated}</div></header>
<main>
<section class="cards">
<div class="card">Total Open<b>{int(stats.get('total_open', 0)):,}</b></div>
<div class="card">Critical<b>{int(stats.get('critical_count', 0)):,}</b></div>
<div class="card">Mean CFS Score<b>{float(stats.get('mean_cfs_score', 0.0)):.2f}</b></div>
<div class="card">Mean Days Open<b>{float(stats.get('mean_days_open', 0.0)):.1f}</b></div>
</section>
<section class="map">{map_html}</section>
<section class="bars"><h2>CFS Tier Distribution</h2>{_tier_bars(stats)}</section>
<section><h2>Top 20 Priority Complaints</h2><table><thead><tr><th>#</th><th>Type</th><th>Description</th><th>District</th><th>Days Open</th><th>Severity</th><th>x Multiplier</th><th>CFS Score</th><th>Tier</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>
</main>
<footer>Generated by UrbanSync · BDI Hackathon 2026 · Team Lorem Ipsum</footer>
</body>
</html>"""


def build_dashboard(queue_path: str | Path, traffic_path: str | Path, stats_path: str | Path, output_path: str | Path) -> None:
    """Load generated outputs and write the final dashboard HTML file."""
    queue_payload = json.loads(Path(queue_path).read_text(encoding="utf-8"))
    queue_list = queue_payload.get("queue", [])
    traffic_df = pd.read_csv(traffic_path)
    stats = json.loads(Path(stats_path).read_text(encoding="utf-8"))
    map_obj = create_map(queue_list[:200], traffic_df)
    html_text = create_dashboard_html(stats, queue_list[:20], map_obj)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_text, encoding="utf-8")
    print(f"Dashboard saved -> {output} ({output.stat().st_size // 1024} KB)")
