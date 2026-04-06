#!/usr/bin/env python3
"""
10_build_heatmap.py
-------------------
Generates an interactive precinct-level choropleth heat map for the
Scott Wiener for Congress campaign (CA CD-11, San Francisco, June 2026 Primary).

Output: dashboard/cd11_heatmap.html  (single self-contained HTML file)
"""

import csv
import io
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

import pandas as pd
import numpy as np

# ── paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_CSV = ROOT / "data" / "processed" / "cd11_voters_with_scores.csv"
GEO_DIR = ROOT / "data" / "geo"
GEO_OUT = GEO_DIR / "sf_precincts.geojson"
DASH_DIR = ROOT / "dashboard"
HTML_OUT = DASH_DIR / "cd11_heatmap.html"

GEO_DIR.mkdir(parents=True, exist_ok=True)
DASH_DIR.mkdir(parents=True, exist_ok=True)


# ── Step 1: Download precinct geometry ───────────────────────────────────────
def download_precinct_data():
    """Download SF precinct boundaries from SF Open Data.
    The dataset 'd6x4-hefw' contains Election Precincts with WKT geometry.
    """
    print("[1/5] Downloading precinct boundaries from SF Open Data ...")

    urls = [
        "https://data.sfgov.org/api/views/d6x4-hefw/rows.csv?accessType=DOWNLOAD",
    ]

    csv_text = None
    for url in urls:
        try:
            print(f"  Trying: {url}")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                csv_text = resp.read().decode("utf-8")
            if csv_text and len(csv_text) > 100:
                print(f"  Downloaded {len(csv_text):,} bytes")
                break
            else:
                csv_text = None
        except Exception as e:
            print(f"  Failed: {e}")
            csv_text = None

    if not csv_text:
        print("  ERROR: Could not download precinct data from any URL.")
        return None

    return csv_text


def parse_wkt_multipolygon(wkt_str):
    """Parse a MULTIPOLYGON WKT string into GeoJSON coordinates."""
    wkt_str = wkt_str.strip()
    if wkt_str.upper().startswith("MULTIPOLYGON"):
        inner = wkt_str[len("MULTIPOLYGON"):].strip()
    elif wkt_str.upper().startswith("POLYGON"):
        inner = wkt_str[len("POLYGON"):].strip()
        # Wrap as multipolygon
        inner = "(" + inner + ")"
    else:
        return None

    # Remove outer parens of MULTIPOLYGON
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1].strip()

    polygons = []
    # Split into individual polygons - they are wrapped in ((...), (...))
    # We need to find matching parentheses
    depth = 0
    current = ""
    for ch in inner:
        if ch == "(":
            depth += 1
            if depth == 1:
                current = ""
                continue
            current += ch
        elif ch == ")":
            depth -= 1
            if depth == 0:
                # Parse this polygon (which may have rings)
                rings = parse_polygon_rings(current)
                if rings:
                    polygons.append(rings)
                current = ""
            else:
                current += ch
        else:
            if depth >= 1:
                current += ch

    if not polygons:
        return None

    return {
        "type": "MultiPolygon",
        "coordinates": polygons,
    }


def parse_polygon_rings(s):
    """Parse the inside of a polygon: (ring1), (ring2), ..."""
    rings = []
    depth = 0
    current = ""
    for ch in s:
        if ch == "(":
            depth += 1
            if depth == 1:
                current = ""
                continue
            current += ch
        elif ch == ")":
            depth -= 1
            if depth == 0:
                ring = parse_ring(current)
                if ring:
                    rings.append(ring)
                current = ""
            else:
                current += ch
        else:
            if depth >= 1:
                current += ch
    return rings if rings else None


def parse_ring(s):
    """Parse a coordinate ring: 'lon lat, lon lat, ...'"""
    coords = []
    for pair in s.split(","):
        pair = pair.strip()
        if not pair:
            continue
        parts = pair.split()
        if len(parts) >= 2:
            try:
                lon = float(parts[0])
                lat = float(parts[1])
                coords.append([lon, lat])
            except ValueError:
                continue
    return coords if len(coords) >= 3 else None


def csv_to_geojson(csv_text):
    """Convert the SF precinct CSV (with WKT geometry) to GeoJSON."""
    print("  Converting WKT geometry to GeoJSON ...")
    reader = csv.DictReader(io.StringIO(csv_text))

    features = []
    for row in reader:
        wkt = row.get("the_geom", "")
        prec = row.get("Prec_2022", "")
        supe = row.get("Supe22", "")
        neigh = row.get("Neigh22", "")

        if not wkt or not prec:
            continue

        geom = parse_wkt_multipolygon(wkt)
        if not geom:
            continue

        features.append({
            "type": "Feature",
            "properties": {
                "precinct": prec,
                "supervisor_district": supe,
                "neighborhood": neigh,
            },
            "geometry": geom,
        })

    geojson = {"type": "FeatureCollection", "features": features}
    print(f"  Parsed {len(features)} precinct polygons")
    return geojson


def build_district_geojson(precinct_geojson):
    """Build supervisor district boundaries by collecting precinct coordinates per district.
    Uses a simple approach: collect all polygon coordinates for each district.
    """
    print("  Building supervisor district boundary overlays ...")
    district_features = {}

    for feat in precinct_geojson["features"]:
        dist = feat["properties"].get("supervisor_district", "")
        if not dist:
            continue
        if dist not in district_features:
            district_features[dist] = []
        # Collect all polygon parts
        geom = feat["geometry"]
        if geom["type"] == "MultiPolygon":
            for poly in geom["coordinates"]:
                district_features[dist].append(poly)
        elif geom["type"] == "Polygon":
            district_features[dist].append(geom["coordinates"])

    features = []
    for dist_id in sorted(district_features.keys(), key=lambda x: int(x) if x.isdigit() else 0):
        coords = district_features[dist_id]
        features.append({
            "type": "Feature",
            "properties": {"district": dist_id},
            "geometry": {"type": "MultiPolygon", "coordinates": coords},
        })

    print(f"  Built {len(features)} district boundary polygons")
    return {"type": "FeatureCollection", "features": features}


def compute_district_centroids(district_geojson):
    """Compute approximate centroids for district labels."""
    centroids = {}
    for feat in district_geojson["features"]:
        dist = feat["properties"]["district"]
        all_lats = []
        all_lons = []
        for poly in feat["geometry"]["coordinates"]:
            for ring in poly:
                for coord in ring:
                    all_lons.append(coord[0])
                    all_lats.append(coord[1])
        if all_lats and all_lons:
            centroids[dist] = [
                sum(all_lats) / len(all_lats),
                sum(all_lons) / len(all_lons),
            ]
    return centroids


# ── Step 2: Load and aggregate voter data ────────────────────────────────────
def aggregate_voter_data():
    """Load voter CSV and aggregate metrics to precinct level."""
    print("[2/5] Loading and aggregating voter data ...")
    df = pd.read_csv(
        DATA_CSV,
        dtype={"PrecinctName": str},
        usecols=[
            "PrecinctName",
            "CountySupervisorName",
            "support_score",
            "turnout_probability",
            "vote_count_6",
            "NonPresPriTO",
            "universe",
            "base_dropoff",
            "persuasion_priority",
            "is_maga",
            "is_saikat_likely",
        ],
        low_memory=False,
    )
    print(f"  Loaded {len(df):,} voter records")

    # Normalize precinct names: strip whitespace, remove leading zeros for matching
    df["PrecinctName"] = df["PrecinctName"].str.strip()

    # Convert boolean columns
    for col in ["base_dropoff", "is_maga", "is_saikat_likely", "persuasion_priority"]:
        if col in df.columns:
            df[col] = df[col].map(
                {True: 1, False: 0, "True": 1, "False": 0, 1: 1, 0: 0}
            ).fillna(0).astype(int)

    # Filter to 4-digit numeric precincts (the ones that match GeoJSON)
    mask = df["PrecinctName"].str.match(r"^\d{4}$", na=False)
    df_matched = df[mask].copy()
    print(f"  Voters with 4-digit precinct: {len(df_matched):,} ({len(df_matched)/len(df)*100:.1f}%)")

    # Aggregate to precinct level
    agg = df_matched.groupby("PrecinctName").agg(
        registered_voters=("PrecinctName", "size"),
        supervisor_district=("CountySupervisorName", "first"),
        support_score_mean=("support_score", "mean"),
        turnout_prob_mean=("NonPresPriTO", "mean"),
        vote_count_mean=("vote_count_6", "mean"),
        total_base=("universe", lambda x: (x == "Base").sum()),
        total_persuasion=("universe", lambda x: (x == "Persuasion").sum()),
        total_opposition=("universe", lambda x: (x == "Opposition").sum()),
        total_base_dropoff=("base_dropoff", "sum"),
        total_maga=("is_maga", "sum"),
        total_saikat=("is_saikat_likely", "sum"),
        total_persuasion_priority=("persuasion_priority", "sum"),
    ).reset_index()

    # Compute percentages
    agg["pct_base"] = (agg["total_base"] / agg["registered_voters"] * 100).round(1)
    agg["pct_opposition"] = (agg["total_opposition"] / agg["registered_voters"] * 100).round(1)
    agg["pct_persuasion"] = (agg["total_persuasion"] / agg["registered_voters"] * 100).round(1)
    agg["pct_maga"] = (agg["total_maga"] / agg["registered_voters"] * 100).round(1)
    agg["pct_saikat"] = (agg["total_saikat"] / agg["registered_voters"] * 100).round(1)
    agg["pct_persuasion_priority"] = (
        agg["total_persuasion_priority"] / agg["registered_voters"] * 100
    ).round(1)

    # Base drop-off as % of base voters (not total)
    agg["pct_base_dropoff"] = np.where(
        agg["total_base"] > 0,
        (agg["total_base_dropoff"] / agg["total_base"] * 100).round(1),
        0,
    )

    # Round means
    agg["support_score_mean"] = agg["support_score_mean"].round(1)
    agg["turnout_prob_mean"] = agg["turnout_prob_mean"].round(1)
    agg["vote_count_mean"] = agg["vote_count_mean"].round(1)

    print(f"  Aggregated to {len(agg)} precincts")
    return agg


# ── Step 3: Merge data with geometry ─────────────────────────────────────────
def merge_data_with_geometry(precinct_geojson, agg_df):
    """Inject aggregated data into GeoJSON feature properties."""
    print("[3/5] Merging voter data with precinct geometry ...")
    data_dict = agg_df.set_index("PrecinctName").to_dict("index")

    matched = 0
    unmatched_geo = []
    for feat in precinct_geojson["features"]:
        prec = feat["properties"]["precinct"]
        if prec in data_dict:
            feat["properties"].update(data_dict[prec])
            matched += 1
        else:
            unmatched_geo.append(prec)
            # Set defaults so JS doesn't crash
            feat["properties"].update({
                "registered_voters": 0,
                "support_score_mean": 0,
                "turnout_prob_mean": 0,
                "vote_count_mean": 0,
                "pct_base": 0,
                "pct_opposition": 0,
                "pct_persuasion": 0,
                "pct_maga": 0,
                "pct_saikat": 0,
                "pct_persuasion_priority": 0,
                "pct_base_dropoff": 0,
                "supervisor_district": feat["properties"].get("supervisor_district", ""),
            })

    data_precincts = set(agg_df["PrecinctName"])
    geo_precincts = set(f["properties"]["precinct"] for f in precinct_geojson["features"])
    unmatched_data = data_precincts - geo_precincts

    print(f"  Matched: {matched} precincts")
    print(f"  GeoJSON precincts without voter data: {len(unmatched_geo)}")
    print(f"  Voter data precincts without geometry: {len(unmatched_data)}")

    return precinct_geojson


# ── Step 4: Build the HTML ───────────────────────────────────────────────────
def build_html(precinct_geojson, district_geojson, district_centroids):
    """Build the complete self-contained HTML/JS/CSS file."""
    print("[4/5] Building interactive HTML map ...")

    # Serialize GeoJSON to compact JSON
    precinct_json = json.dumps(precinct_geojson, separators=(",", ":"))
    district_json = json.dumps(district_geojson, separators=(",", ":"))
    centroids_json = json.dumps(district_centroids, separators=(",", ":"))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Scott Wiener for Congress &mdash; CD-11 Precinct Heatmap</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
    font-family: 'Montserrat', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f5f0eb;
    color: #1B2A4A;
    line-height: 1.5;
    font-size: 14px;
}}

/* Rainbow stripe */
.rainbow-stripe {{
    height: 6px;
    background: linear-gradient(90deg,
        #e24040 0%, #e24040 16.66%,
        #f28c28 16.66%, #f28c28 33.33%,
        #f5d23b 33.33%, #f5d23b 50%,
        #4caf50 50%, #4caf50 66.66%,
        #2196f3 66.66%, #2196f3 83.33%,
        #9c27b0 83.33%, #9c27b0 100%);
}}

/* Header */
.header {{
    background: #1B2A4A;
    color: #fff;
    padding: 16px 24px 14px;
    text-align: center;
}}
.header h1 {{
    font-size: 20px;
    font-weight: 800;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}
.header h1 .gold {{ color: #E8A630; }}
.header .subtitle {{
    font-size: 12px;
    color: #E8A630;
    font-weight: 600;
    letter-spacing: 1px;
    margin-top: 2px;
}}

/* Map container */
#map {{
    width: 100%;
    height: calc(100vh - 80px);
}}

/* Control panel - top right */
.control-panel {{
    position: absolute;
    top: 100px;
    right: 16px;
    z-index: 1000;
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.2);
    padding: 14px;
    width: 250px;
    max-height: calc(100vh - 200px);
    overflow-y: auto;
    font-size: 12px;
}}
.control-panel h3 {{
    font-size: 13px;
    font-weight: 700;
    color: #1B2A4A;
    margin-bottom: 10px;
    border-bottom: 2px solid #E8A630;
    padding-bottom: 4px;
}}
.layer-group {{
    margin-bottom: 10px;
}}
.layer-group-title {{
    font-size: 11px;
    font-weight: 700;
    color: #E8A630;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
}}
.layer-option {{
    display: flex;
    align-items: center;
    padding: 3px 0;
    cursor: pointer;
}}
.layer-option:hover {{
    background: #f5f0eb;
    border-radius: 4px;
}}
.layer-option input {{
    margin-right: 6px;
    accent-color: #1B2A4A;
}}
.layer-option label {{
    cursor: pointer;
    font-size: 12px;
}}

/* Search box */
.search-box {{
    position: absolute;
    top: 100px;
    left: 16px;
    z-index: 1000;
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.2);
    padding: 10px;
    width: 220px;
}}
.search-box input {{
    width: 100%;
    padding: 6px 10px;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    font-family: inherit;
    font-size: 12px;
    outline: none;
}}
.search-box input:focus {{
    border-color: #E8A630;
    box-shadow: 0 0 0 2px rgba(232,166,48,0.2);
}}
.search-results {{
    max-height: 200px;
    overflow-y: auto;
    margin-top: 6px;
}}
.search-result-item {{
    padding: 4px 8px;
    font-size: 11px;
    cursor: pointer;
    border-radius: 3px;
}}
.search-result-item:hover {{
    background: #E8A630;
    color: white;
}}

/* Legend */
.legend {{
    position: absolute;
    bottom: 30px;
    left: 16px;
    z-index: 1000;
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.2);
    padding: 12px 14px;
    min-width: 180px;
}}
.legend h4 {{
    font-size: 12px;
    font-weight: 700;
    color: #1B2A4A;
    margin-bottom: 6px;
}}
.legend-bar {{
    width: 160px;
    height: 14px;
    border-radius: 3px;
    margin-bottom: 4px;
}}
.legend-labels {{
    display: flex;
    justify-content: space-between;
    font-size: 10px;
    color: #64748b;
}}

/* District labels */
.district-label {{
    font-family: 'Montserrat', sans-serif;
    font-size: 14px;
    font-weight: 800;
    color: #1B2A4A;
    text-shadow: 1px 1px 2px white, -1px -1px 2px white, 1px -1px 2px white, -1px 1px 2px white;
    white-space: nowrap;
}}

/* Custom tooltip styling */
.precinct-tooltip {{
    font-family: 'Montserrat', sans-serif;
    font-size: 11px;
    line-height: 1.4;
    padding: 6px 10px;
    background: white;
    border: 1px solid #1B2A4A;
    border-radius: 4px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}}
.precinct-tooltip strong {{
    color: #1B2A4A;
}}
.precinct-tooltip .gold {{
    color: #E8A630;
    font-weight: 600;
}}

/* Popup */
.leaflet-popup-content {{
    font-family: 'Montserrat', sans-serif;
    font-size: 12px;
    line-height: 1.5;
    min-width: 220px;
}}
.popup-title {{
    font-size: 14px;
    font-weight: 800;
    color: #1B2A4A;
    border-bottom: 2px solid #E8A630;
    padding-bottom: 4px;
    margin-bottom: 6px;
}}
.popup-section {{
    margin-bottom: 4px;
}}
.popup-section strong {{
    color: #1B2A4A;
}}
.popup-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 2px 12px;
}}
.popup-row {{
    display: flex;
    justify-content: space-between;
}}
.popup-label {{ color: #64748b; }}
.popup-value {{ font-weight: 600; color: #1B2A4A; }}

/* Overlay toggle */
.overlay-toggle {{
    position: absolute;
    bottom: 30px;
    right: 16px;
    z-index: 1000;
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.2);
    padding: 10px 14px;
    font-size: 12px;
}}
.overlay-toggle label {{
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
}}
.overlay-toggle input {{
    accent-color: #1B2A4A;
}}
</style>
</head>
<body>

<div class="rainbow-stripe"></div>
<div class="header">
    <h1>Scott Wiener <span class="gold">for Congress</span></h1>
    <div class="subtitle">CA CD-11 &bull; Precinct-Level Heatmap &bull; June 2026 Primary</div>
</div>

<div id="map"></div>

<!-- Search box -->
<div class="search-box">
    <input type="text" id="searchInput" placeholder="Search precinct or district..." />
    <div class="search-results" id="searchResults"></div>
</div>

<!-- Layer selector -->
<div class="control-panel">
    <h3>Map Layers</h3>
    <div class="layer-group">
        <div class="layer-group-title">Support Model</div>
        <div class="layer-option">
            <input type="radio" name="layer" id="layer_support" value="support_score_mean" checked>
            <label for="layer_support">Support Score</label>
        </div>
        <div class="layer-option">
            <input type="radio" name="layer" id="layer_base" value="pct_base">
            <label for="layer_base">Base %</label>
        </div>
        <div class="layer-option">
            <input type="radio" name="layer" id="layer_dropoff" value="pct_base_dropoff">
            <label for="layer_dropoff">Base Drop-off %</label>
        </div>
        <div class="layer-option">
            <input type="radio" name="layer" id="layer_opp" value="pct_opposition">
            <label for="layer_opp">Opposition %</label>
        </div>
        <div class="layer-option">
            <input type="radio" name="layer" id="layer_persuasion" value="pct_persuasion_priority">
            <label for="layer_persuasion">Persuasion Priority %</label>
        </div>
    </div>
    <div class="layer-group">
        <div class="layer-group-title">Turnout Model</div>
        <div class="layer-option">
            <input type="radio" name="layer" id="layer_turnout" value="turnout_prob_mean">
            <label for="layer_turnout">Turnout Probability</label>
        </div>
        <div class="layer-option">
            <input type="radio" name="layer" id="layer_votefreq" value="vote_count_mean">
            <label for="layer_votefreq">Vote Frequency</label>
        </div>
        <div class="layer-option">
            <input type="radio" name="layer" id="layer_regvot" value="registered_voters">
            <label for="layer_regvot">Registered Voters</label>
        </div>
        <div class="layer-option">
            <input type="radio" name="layer" id="layer_maga" value="pct_maga">
            <label for="layer_maga">MAGA Density %</label>
        </div>
        <div class="layer-option">
            <input type="radio" name="layer" id="layer_saikat" value="pct_saikat">
            <label for="layer_saikat">Saikat-likely %</label>
        </div>
    </div>
</div>

<!-- Legend -->
<div class="legend" id="legend">
    <h4 id="legendTitle">Support Score</h4>
    <div class="legend-bar" id="legendBar"></div>
    <div class="legend-labels">
        <span id="legendMin">0</span>
        <span id="legendMax">100</span>
    </div>
</div>

<!-- District boundary overlay toggle -->
<div class="overlay-toggle">
    <label>
        <input type="checkbox" id="districtToggle" checked>
        District boundaries
    </label>
    <label style="margin-top:4px;">
        <input type="checkbox" id="labelToggle" checked>
        District labels
    </label>
</div>

<script>
// ── Embedded data ──────────────────────────────────────────────────
var PRECINCT_DATA = {precinct_json};
var DISTRICT_DATA = {district_json};
var DISTRICT_CENTROIDS = {centroids_json};

// ── Layer configuration ────────────────────────────────────────────
var LAYERS = {{
    support_score_mean: {{
        title: "Support Score (Mean)",
        colorHigh: "#1B2A4A",
        min: 0, max: 100,
        format: function(v) {{ return v.toFixed(1); }},
        unit: ""
    }},
    pct_base: {{
        title: "Base % (Universe)",
        colorHigh: "#059669",
        min: 0, max: 70,
        format: function(v) {{ return v.toFixed(1) + "%"; }},
        unit: "%"
    }},
    pct_base_dropoff: {{
        title: "Base Drop-off % (GOTV Need)",
        colorHigh: "#dc2626",
        min: 0, max: 80,
        format: function(v) {{ return v.toFixed(1) + "%"; }},
        unit: "%"
    }},
    pct_opposition: {{
        title: "Opposition %",
        colorHigh: "#475569",
        min: 0, max: 60,
        format: function(v) {{ return v.toFixed(1) + "%"; }},
        unit: "%"
    }},
    pct_persuasion_priority: {{
        title: "Persuasion Priority %",
        colorHigh: "#E8A630",
        min: 0, max: 60,
        format: function(v) {{ return v.toFixed(1) + "%"; }},
        unit: "%"
    }},
    turnout_prob_mean: {{
        title: "Turnout Probability (Mean)",
        colorHigh: "#0891b2",
        min: 0, max: 100,
        format: function(v) {{ return v.toFixed(1); }},
        unit: ""
    }},
    vote_count_mean: {{
        title: "Vote Frequency (Mean of 6)",
        colorHigh: "#7c3aed",
        min: 0, max: 6,
        format: function(v) {{ return v.toFixed(1); }},
        unit: ""
    }},
    registered_voters: {{
        title: "Registered Voters",
        colorHigh: "#4f46e5",
        min: 0, max: 3000,
        format: function(v) {{ return Math.round(v).toLocaleString(); }},
        unit: ""
    }},
    pct_maga: {{
        title: "MAGA Density %",
        colorHigh: "#dc2626",
        min: 0, max: 30,
        format: function(v) {{ return v.toFixed(1) + "%"; }},
        unit: "%"
    }},
    pct_saikat: {{
        title: "Saikat-likely %",
        colorHigh: "#d97706",
        min: 0, max: 15,
        format: function(v) {{ return v.toFixed(1) + "%"; }},
        unit: "%"
    }}
}};

// ── Color utilities ────────────────────────────────────────────────
function hexToRgb(hex) {{
    var r = parseInt(hex.slice(1,3), 16);
    var g = parseInt(hex.slice(3,5), 16);
    var b = parseInt(hex.slice(5,7), 16);
    return [r, g, b];
}}

function interpolateColor(t, highHex) {{
    // t: 0 (white) to 1 (highColor)
    t = Math.max(0, Math.min(1, t));
    var high = hexToRgb(highHex);
    var r = Math.round(255 + (high[0] - 255) * t);
    var g = Math.round(255 + (high[1] - 255) * t);
    var b = Math.round(255 + (high[2] - 255) * t);
    return "rgb(" + r + "," + g + "," + b + ")";
}}

function getColor(value, layerKey) {{
    var cfg = LAYERS[layerKey];
    if (value === undefined || value === null || isNaN(value)) return "#e2e8f0";
    var t = (value - cfg.min) / (cfg.max - cfg.min);
    return interpolateColor(t, cfg.colorHigh);
}}

// ── Initialize map ─────────────────────────────────────────────────
var map = L.map("map", {{
    center: [37.76, -122.44],
    zoom: 12,
    zoomControl: true,
}});

L.tileLayer("https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}@2x.png", {{
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
    subdomains: "abcd",
    maxZoom: 19,
}}).addTo(map);

// ── Current state ──────────────────────────────────────────────────
var currentLayer = "support_score_mean";
var precinctLayer = null;
var districtLayer = null;
var labelLayer = null;
var highlightedFeature = null;

// ── Tooltip & popup content ────────────────────────────────────────
function buildTooltip(props) {{
    var dist = props.supervisor_district || props.district || "?";
    var name = "Precinct " + (props.precinct || "?");
    var neigh = props.neighborhood || "";
    var html = '<div class="precinct-tooltip">';
    html += "<strong>" + name + "</strong>";
    if (neigh) html += " &mdash; " + neigh;
    html += '<br><span class="gold">District ' + dist + "</span>";
    html += "<br>Voters: <strong>" + (props.registered_voters || 0).toLocaleString() + "</strong>";
    html += "<br>Support: <strong>" + (props.support_score_mean || 0).toFixed(1) + "</strong>";
    html += "<br>Turnout: <strong>" + (props.turnout_prob_mean || 0).toFixed(1) + "</strong>";
    html += "</div>";
    return html;
}}

function buildPopup(props) {{
    var dist = props.supervisor_district || props.district || "?";
    var name = "Precinct " + (props.precinct || "?");
    var neigh = props.neighborhood || "";
    var html = '<div class="popup-title">' + name + "</div>";
    if (neigh) html += '<div style="color:#64748b;font-size:11px;margin-bottom:6px;">' + neigh + ' &bull; District ' + dist + '</div>';
    else html += '<div style="color:#64748b;font-size:11px;margin-bottom:6px;">District ' + dist + '</div>';

    html += '<div class="popup-grid">';
    var rows = [
        ["Reg. Voters", (props.registered_voters || 0).toLocaleString()],
        ["Support Score", (props.support_score_mean || 0).toFixed(1)],
        ["Turnout Prob.", (props.turnout_prob_mean || 0).toFixed(1)],
        ["Vote Freq.", (props.vote_count_mean || 0).toFixed(1)],
        ["Base %", (props.pct_base || 0).toFixed(1) + "%"],
        ["Persuasion %", (props.pct_persuasion || 0).toFixed(1) + "%"],
        ["Opposition %", (props.pct_opposition || 0).toFixed(1) + "%"],
        ["Drop-off %", (props.pct_base_dropoff || 0).toFixed(1) + "%"],
        ["Persuasion Prio.", (props.pct_persuasion_priority || 0).toFixed(1) + "%"],
        ["MAGA %", (props.pct_maga || 0).toFixed(1) + "%"],
        ["Saikat %", (props.pct_saikat || 0).toFixed(1) + "%"],
    ];
    for (var i = 0; i < rows.length; i++) {{
        html += '<div class="popup-row"><span class="popup-label">' + rows[i][0] + '</span><span class="popup-value">' + rows[i][1] + '</span></div>';
    }}
    html += "</div>";
    return html;
}}

// ── Render precinct layer ──────────────────────────────────────────
function styleFeature(feature) {{
    var val = feature.properties[currentLayer];
    return {{
        fillColor: getColor(val, currentLayer),
        fillOpacity: 0.75,
        weight: 0.5,
        color: "#94a3b8",
        opacity: 0.6,
    }};
}}

function highlightFeature(e) {{
    var layer = e.target;
    layer.setStyle({{
        weight: 2,
        color: "#E8A630",
        fillOpacity: 0.9,
    }});
    layer.bringToFront();
    if (districtLayer) districtLayer.bringToFront();
}}

function resetHighlight(e) {{
    precinctLayer.resetStyle(e.target);
}}

function onEachFeature(feature, layer) {{
    layer.bindTooltip(buildTooltip(feature.properties), {{
        className: "precinct-tooltip",
        sticky: true,
    }});
    layer.bindPopup(buildPopup(feature.properties), {{
        maxWidth: 280,
    }});
    layer.on({{
        mouseover: highlightFeature,
        mouseout: resetHighlight,
    }});
}}

function renderPrecincts() {{
    if (precinctLayer) {{
        map.removeLayer(precinctLayer);
    }}
    precinctLayer = L.geoJSON(PRECINCT_DATA, {{
        style: styleFeature,
        onEachFeature: onEachFeature,
    }}).addTo(map);

    // Re-add district overlay on top
    if (districtLayer && document.getElementById("districtToggle").checked) {{
        districtLayer.bringToFront();
    }}
}}

// ── District boundary overlay ──────────────────────────────────────
function renderDistrictBoundaries() {{
    if (districtLayer) {{
        map.removeLayer(districtLayer);
        districtLayer = null;
    }}
    districtLayer = L.geoJSON(DISTRICT_DATA, {{
        style: {{
            fillColor: "transparent",
            fillOpacity: 0,
            weight: 3,
            color: "#1B2A4A",
            opacity: 0.7,
            dashArray: "6,4",
        }},
        interactive: false,
    }}).addTo(map);
}}

function renderDistrictLabels() {{
    if (labelLayer) {{
        map.removeLayer(labelLayer);
        labelLayer = null;
    }}
    labelLayer = L.layerGroup();
    for (var dist in DISTRICT_CENTROIDS) {{
        var c = DISTRICT_CENTROIDS[dist];
        var marker = L.marker(c, {{
            icon: L.divIcon({{
                className: "district-label",
                html: "D" + dist,
                iconSize: [40, 20],
                iconAnchor: [20, 10],
            }}),
            interactive: false,
        }});
        labelLayer.addLayer(marker);
    }}
    labelLayer.addTo(map);
}}

// ── Legend ──────────────────────────────────────────────────────────
function updateLegend() {{
    var cfg = LAYERS[currentLayer];
    document.getElementById("legendTitle").textContent = cfg.title;
    document.getElementById("legendMin").textContent = cfg.min + (cfg.unit || "");
    document.getElementById("legendMax").textContent = cfg.max + (cfg.unit || "");

    // Build gradient
    var stops = [];
    for (var i = 0; i <= 10; i++) {{
        var t = i / 10;
        stops.push(interpolateColor(t, cfg.colorHigh) + " " + (t * 100) + "%");
    }}
    document.getElementById("legendBar").style.background =
        "linear-gradient(to right, " + stops.join(", ") + ")";
}}

// ── Search ─────────────────────────────────────────────────────────
var searchInput = document.getElementById("searchInput");
var searchResults = document.getElementById("searchResults");

// Build search index
var searchIndex = [];
PRECINCT_DATA.features.forEach(function(f) {{
    searchIndex.push({{
        label: "Precinct " + f.properties.precinct +
            (f.properties.neighborhood ? " (" + f.properties.neighborhood + ")" : "") +
            " - D" + (f.properties.supervisor_district || "?"),
        precinct: f.properties.precinct,
        type: "precinct",
    }});
}});
for (var d in DISTRICT_CENTROIDS) {{
    searchIndex.push({{
        label: "District " + d,
        district: d,
        type: "district",
    }});
}}

searchInput.addEventListener("input", function() {{
    var query = this.value.toLowerCase().trim();
    searchResults.innerHTML = "";
    if (!query) return;

    var matches = searchIndex.filter(function(item) {{
        return item.label.toLowerCase().indexOf(query) >= 0;
    }}).slice(0, 15);

    matches.forEach(function(item) {{
        var div = document.createElement("div");
        div.className = "search-result-item";
        div.textContent = item.label;
        div.addEventListener("click", function() {{
            if (item.type === "precinct") {{
                // Find and zoom to precinct
                precinctLayer.eachLayer(function(layer) {{
                    if (layer.feature.properties.precinct === item.precinct) {{
                        map.fitBounds(layer.getBounds(), {{ maxZoom: 15 }});
                        layer.openPopup();
                    }}
                }});
            }} else if (item.type === "district") {{
                var c = DISTRICT_CENTROIDS[item.district];
                if (c) map.setView(c, 14);
            }}
            searchResults.innerHTML = "";
            searchInput.value = "";
        }});
        searchResults.appendChild(div);
    }});
}});

// ── Event handlers ─────────────────────────────────────────────────
document.querySelectorAll('input[name="layer"]').forEach(function(radio) {{
    radio.addEventListener("change", function() {{
        currentLayer = this.value;
        renderPrecincts();
        updateLegend();
    }});
}});

document.getElementById("districtToggle").addEventListener("change", function() {{
    if (this.checked) {{
        renderDistrictBoundaries();
    }} else if (districtLayer) {{
        map.removeLayer(districtLayer);
        districtLayer = null;
    }}
}});

document.getElementById("labelToggle").addEventListener("change", function() {{
    if (this.checked) {{
        renderDistrictLabels();
    }} else if (labelLayer) {{
        map.removeLayer(labelLayer);
        labelLayer = null;
    }}
}});

// ── Initial render ─────────────────────────────────────────────────
renderPrecincts();
renderDistrictBoundaries();
renderDistrictLabels();
updateLegend();

</script>
</body>
</html>"""

    return html


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  CD-11 Precinct Heatmap Builder")
    print("=" * 60)

    # Step 1: Get geometry
    csv_text = download_precinct_data()
    if csv_text is None:
        print("\nFATAL: Could not download precinct geometry. Exiting.")
        sys.exit(1)

    precinct_geojson = csv_to_geojson(csv_text)

    # Save GeoJSON
    with open(GEO_OUT, "w") as f:
        json.dump(precinct_geojson, f)
    geo_size = os.path.getsize(GEO_OUT)
    print(f"  Saved GeoJSON: {GEO_OUT} ({geo_size:,} bytes)")

    # Build district boundaries
    district_geojson = build_district_geojson(precinct_geojson)
    district_centroids = compute_district_centroids(district_geojson)

    # Step 2: Aggregate voter data
    agg_df = aggregate_voter_data()

    # Step 3: Merge
    precinct_geojson = merge_data_with_geometry(precinct_geojson, agg_df)

    # Step 4: Build HTML
    html = build_html(precinct_geojson, district_geojson, district_centroids)

    # Step 5: Write output
    print("[5/5] Writing HTML output ...")
    with open(HTML_OUT, "w", encoding="utf-8") as f:
        f.write(html)
    html_size = os.path.getsize(HTML_OUT)
    print(f"  Output: {HTML_OUT}")
    print(f"  File size: {html_size:,} bytes ({html_size/1024/1024:.1f} MB)")
    print()
    print("Done! Open the HTML file in a browser to view the map.")


if __name__ == "__main__":
    main()
