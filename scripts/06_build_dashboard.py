#!/usr/bin/env python3
"""
Step 6: Build Interactive HTML Dashboard
==========================================
Generates a single self-contained HTML dashboard for the SF CD-11 voter
turnout model.  ALL data is embedded as JavaScript variables so the file
works offline (except for the Chart.js CDN).

Input:  data/processed/turnout_scenarios.csv
        data/processed/demographic_scenarios.csv
        data/processed/historical_turnout_rates.csv
        data/processed/precinct_universe.csv

Output: dashboard/turnout_dashboard.html

To install required packages:
    pip install pandas numpy

To run:
    python scripts/06_build_dashboard.py
"""

import base64
import json
import os
import pandas as pd
import numpy as np

# ── FILE PATHS ────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data", "processed")
OUTPUT_DIR = os.path.join(BASE_DIR, "dashboard")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "turnout_dashboard.html")

TURNOUT_SCENARIOS = os.path.join(DATA_DIR, "turnout_scenarios.csv")
DEMOGRAPHIC_SCENARIOS = os.path.join(DATA_DIR, "demographic_scenarios.csv")
HISTORICAL_RATES = os.path.join(DATA_DIR, "historical_turnout_rates.csv")
PRECINCT_UNIVERSE = os.path.join(DATA_DIR, "precinct_universe.csv")
LOGO_FILE = os.path.join(BASE_DIR, "assets", "wiener_logo.jpg")

# ── LOAD DATA ─────────────────────────────────────────────────────────────────
print("=" * 70)
print("STEP 6: BUILD INTERACTIVE DASHBOARD")
print("=" * 70)

print("\nLoading data files...")

# Load campaign logo as base64 data URI
with open(LOGO_FILE, "rb") as f:
    logo_b64 = base64.b64encode(f.read()).decode("utf-8")
LOGO_DATA_URI = f"data:image/jpeg;base64,{logo_b64}"

scenarios = pd.read_csv(TURNOUT_SCENARIOS, dtype={"PrecinctName": str})
demographics = pd.read_csv(DEMOGRAPHIC_SCENARIOS)
historical = pd.read_csv(HISTORICAL_RATES, dtype={"PrecinctName": str})
universe = pd.read_csv(PRECINCT_UNIVERSE, dtype={"PrecinctName": str})

print(f"  turnout_scenarios.csv:     {len(scenarios):,} rows")
print(f"  demographic_scenarios.csv: {len(demographics):,} rows")
print(f"  historical_turnout_rates:  {len(historical):,} rows")
print(f"  precinct_universe.csv:     {len(universe):,} rows")

# ── BUILD GEOGRAPHIC SUMMARIES ────────────────────────────────────────────────
print("\nBuilding geographic summaries...")

# Historical citywide rates (weighted by registered voters in each election)
hist_cols = {
    "jun2018": ("turnout_primary_jun2018", "voted_primary_jun2018", "registered_primary_jun2018"),
    "jun2022": ("turnout_primary_jun2022", "voted_primary_jun2022", "registered_primary_jun2022"),
    "mar2024": ("turnout_primary_mar2024", "voted_primary_mar2024", "registered_primary_mar2024"),
    "nov2018": ("turnout_general_nov2018", "voted_general_nov2018", "registered_general_nov2018"),
    "nov2022": ("turnout_general_nov2022", "voted_general_nov2022", "registered_general_nov2022"),
    "nov2024": ("turnout_general_nov2024", "voted_general_nov2024", "registered_general_nov2024"),
}


def compute_historical_rate(df, voted_col, registered_col):
    """Compute aggregate turnout rate from vote/registered columns."""
    voted = df[voted_col].sum()
    registered = df[registered_col].sum()
    if registered > 0 and not np.isnan(voted) and not np.isnan(registered):
        return voted / registered
    return None


def build_geo_summary(sub_scenarios, sub_historical, geo_label):
    """Build summary rows for a single geography."""
    rows = []
    for election_type in ["primary", "general"]:
        # Compute historical rates for this geography
        hist_jun2018 = compute_historical_rate(
            sub_historical, "voted_primary_jun2018", "registered_primary_jun2018"
        ) if "voted_primary_jun2018" in sub_historical.columns else None
        hist_jun2022 = compute_historical_rate(
            sub_historical, "voted_primary_jun2022", "registered_primary_jun2022"
        )
        hist_mar2024 = compute_historical_rate(
            sub_historical, "voted_primary_mar2024", "registered_primary_mar2024"
        )
        hist_nov2018 = compute_historical_rate(
            sub_historical, "voted_general_nov2018", "registered_general_nov2018"
        ) if "voted_general_nov2018" in sub_historical.columns else None
        hist_nov2022 = compute_historical_rate(
            sub_historical, "voted_general_nov2022", "registered_general_nov2022"
        )
        hist_nov2024 = compute_historical_rate(
            sub_historical, "voted_general_nov2024", "registered_general_nov2024"
        )

        for scenario in ["HIGH", "EXPECTED", "LOW"]:
            subset = sub_scenarios[
                (sub_scenarios["election_type"] == election_type)
                & (sub_scenarios["scenario"] == scenario)
            ]
            reg = int(subset["registered_voters"].sum())
            bal = int(subset["estimated_ballots"].sum())
            pct = bal / reg if reg > 0 else 0.0

            row = {
                "geography": geo_label,
                "election_type": election_type,
                "scenario": scenario,
                "registered_voters": reg,
                "estimated_ballots": bal,
                "estimated_turnout_pct": round(pct, 4),
                "historical_jun2018_pct": round(hist_jun2018, 4)
                if hist_jun2018 is not None
                else None,
                "historical_jun2022_pct": round(hist_jun2022, 4)
                if hist_jun2022 is not None
                else None,
                "historical_mar2024_pct": round(hist_mar2024, 4)
                if hist_mar2024 is not None
                else None,
                "historical_nov2018_pct": round(hist_nov2018, 4)
                if hist_nov2018 is not None
                else None,
                "historical_nov2022_pct": round(hist_nov2022, 4)
                if hist_nov2022 is not None
                else None,
                "historical_nov2024_pct": round(hist_nov2024, 4)
                if hist_nov2024 is not None
                else None,
            }

            # Compute vs-historical deltas
            row["vs_jun2018"] = (
                round(pct - hist_jun2018, 4)
                if hist_jun2018 is not None
                else None
            )
            row["vs_jun2022"] = (
                round(pct - hist_jun2022, 4)
                if hist_jun2022 is not None
                else None
            )
            row["vs_mar2024"] = (
                round(pct - hist_mar2024, 4)
                if hist_mar2024 is not None
                else None
            )
            row["vs_nov2018"] = (
                round(pct - hist_nov2018, 4)
                if hist_nov2018 is not None
                else None
            )
            row["vs_nov2022"] = (
                round(pct - hist_nov2022, 4)
                if hist_nov2022 is not None
                else None
            )
            row["vs_nov2024"] = (
                round(pct - hist_nov2024, 4)
                if hist_nov2024 is not None
                else None
            )
            rows.append(row)
    return rows


geo_rows = []

# Citywide
geo_rows.extend(build_geo_summary(scenarios, historical, "Citywide"))

# CD11 (all precincts where in_cd11 == True)
cd11_scenarios = scenarios[scenarios["in_cd11"] == True]
cd11_historical = historical[historical["in_cd11"] == True]
geo_rows.extend(build_geo_summary(cd11_scenarios, cd11_historical, "CD11"))

# Each supervisor district
for dist in sorted(scenarios["sup_district"].unique()):
    dist_scenarios = scenarios[scenarios["sup_district"] == dist]
    dist_historical = historical[historical["sup_district"] == dist]
    geo_rows.extend(
        build_geo_summary(dist_scenarios, dist_historical, f"Sup_{int(dist):02d}")
    )

geo_summary = pd.DataFrame(geo_rows)
print(f"  Geographic summary: {len(geo_summary)} rows")

# ── SAVE GEOGRAPHIC SUMMARIES (also useful independently) ─────────────────────
geo_summary_path = os.path.join(DATA_DIR, "geographic_summary.csv")
geo_summary.to_csv(geo_summary_path, index=False)
print(f"  Saved geographic_summary.csv")

# ── BUILD GEOGRAPHIC-DEMOGRAPHIC SUMMARIES ────────────────────────────────────
print("Building geographic-demographic summaries...")

# We need per-geography demographic breakdowns. The demographic_scenarios.csv
# is citywide only, so we recompute from precinct-level data for each geography.

# Merge scenarios with universe to get demographic columns
scenario_with_demo = scenarios.merge(
    universe[
        [
            "PrecinctName",
            "age_18-29",
            "age_30-44",
            "age_45-64",
            "age_65+",
            "race_Asian",
            "race_Black",
            "race_Latino/Hispanic",
            "race_White",
            "race_Other/Unknown",
            "party_Democrat",
            "party_NPP",
            "party_Other",
            "party_Republican",
        ]
    ],
    on="PrecinctName",
    how="left",
)

demo_groups = {
    "age": ["18-29", "30-44", "45-64", "65+"],
    "race": ["Asian", "Black", "Latino/Hispanic", "White", "Other/Unknown"],
    "party": ["Democrat", "NPP", "Other", "Republican"],
}


def build_geo_demo_summary(sub_data, geo_label):
    """Build demographic breakdown rows for a single geography."""
    rows = []
    for election_type in ["primary", "general"]:
        for scenario in ["HIGH", "EXPECTED", "LOW"]:
            subset = sub_data[
                (sub_data["election_type"] == election_type)
                & (sub_data["scenario"] == scenario)
            ]
            for dimension, groups in demo_groups.items():
                for group in groups:
                    col = f"{dimension}_{group}"
                    if col not in subset.columns:
                        continue
                    group_reg = int(subset[col].sum())
                    # Estimated ballots for this group: group_count * precinct turnout rate
                    group_ballots = int(
                        (subset[col] * subset["estimated_turnout_pct"]).sum()
                    )
                    group_pct = group_ballots / group_reg if group_reg > 0 else 0.0
                    total_reg = int(subset["registered_voters"].sum())
                    pct_of_geo = group_reg / total_reg if total_reg > 0 else 0.0

                    rows.append(
                        {
                            "geography": geo_label,
                            "election_type": election_type,
                            "scenario": scenario,
                            "dimension": dimension,
                            "group": group,
                            "registered_in_group": group_reg,
                            "pct_of_geography": round(pct_of_geo, 4),
                            "estimated_ballots": group_ballots,
                            "estimated_turnout_pct": round(group_pct, 4),
                        }
                    )
    return rows


geo_demo_rows = []
geo_demo_rows.extend(build_geo_demo_summary(scenario_with_demo, "Citywide"))

cd11_data = scenario_with_demo[scenario_with_demo["in_cd11"] == True]
geo_demo_rows.extend(build_geo_demo_summary(cd11_data, "CD11"))

for dist in sorted(scenarios["sup_district"].unique()):
    dist_data = scenario_with_demo[scenario_with_demo["sup_district"] == dist]
    geo_demo_rows.extend(
        build_geo_demo_summary(dist_data, f"Sup_{int(dist):02d}")
    )

geo_demo_summary = pd.DataFrame(geo_demo_rows)
print(f"  Geographic-demographic summary: {len(geo_demo_summary)} rows")

geo_demo_path = os.path.join(DATA_DIR, "geographic_demographic_summary.csv")
geo_demo_summary.to_csv(geo_demo_path, index=False)
print(f"  Saved geographic_demographic_summary.csv")


# ── CONVERT DATA TO JSON FOR EMBEDDING ────────────────────────────────────────
print("\nConverting data to JSON for embedding...")


def sanitize_for_json(df):
    """Replace NaN/None with null-safe values for JSON serialization."""
    df = df.copy()
    df = df.where(pd.notnull(df), None)
    records = df.to_dict(orient="records")
    # Convert None to explicit null for JSON
    return json.dumps(records, default=str)


geo_json = sanitize_for_json(geo_summary)
geo_demo_json = sanitize_for_json(geo_demo_summary)

# For precinct data, include only the columns needed for the dashboard
precinct_cols = [
    "PrecinctName",
    "sup_district",
    "in_cd11",
    "election_type",
    "scenario",
    "registered_voters",
    "estimated_ballots",
    "estimated_turnout_pct",
]
# Filter out precincts with fewer than 100 registered voters (data errors)
precinct_filtered = scenarios[scenarios["registered_voters"] >= 100]
precinct_json = sanitize_for_json(precinct_filtered[precinct_cols])

# Citywide demographic scenarios (from the original file)
demo_json = sanitize_for_json(demographics)

print(f"  Geographic JSON:    {len(geo_json):>10,} chars")
print(f"  Geo-Demographic:    {len(geo_demo_json):>10,} chars")
print(f"  Precinct JSON:      {len(precinct_json):>10,} chars")
print(f"  Demographic JSON:   {len(demo_json):>10,} chars")


# ── GENERATE HTML ─────────────────────────────────────────────────────────────
print("\nGenerating HTML dashboard...")

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Scott Wiener for Congress &mdash; CD-11 Voter Turnout Model</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
/* ── RESET & BASE ───────────────────────────────────────────────── */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
    font-family: 'Montserrat', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
                 Oxygen, Ubuntu, Cantarell, sans-serif;
    background: #f5f0eb;
    color: #1B2A4A;
    line-height: 1.5;
    font-size: 14px;
}}

/* ── RAINBOW STRIPE ────────────────────────────────────────────── */
.rainbow-stripe {{
    height: 6px;
    background: linear-gradient(90deg, #e24040 0%, #e24040 16.66%, #f28c28 16.66%, #f28c28 33.33%, #f5d23b 33.33%, #f5d23b 50%, #4caf50 50%, #4caf50 66.66%, #2196f3 66.66%, #2196f3 83.33%, #9c27b0 83.33%, #9c27b0 100%);
}}

/* ── HEADER ─────────────────────────────────────────────────────── */
.header {{
    background: #1B2A4A;
    color: #fff;
    padding: 24px 32px 20px;
    text-align: center;
}}
.header h1 {{
    font-size: 24px;
    font-weight: 800;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
    text-transform: uppercase;
}}
.header h1 .gold {{
    color: #E8A630;
}}
.header .subtitle {{
    font-size: 14px;
    color: #E8A630;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
}}
.header .logo {{
    max-height: 80px;
    margin-bottom: 12px;
}}

/* ── CONTROL BAR ────────────────────────────────────────────────── */
.controls {{
    position: sticky;
    top: 0;
    z-index: 100;
    background: #fff;
    border-bottom: 1px solid #d1d5db;
    padding: 12px 32px;
    display: flex;
    flex-wrap: wrap;
    gap: 24px;
    align-items: center;
    box-shadow: 0 2px 4px rgba(0,0,0,0.06);
}}
.control-group {{
    display: flex;
    align-items: center;
    gap: 8px;
}}
.control-group label {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #6b7280;
    font-weight: 600;
    white-space: nowrap;
}}
.control-group select {{
    padding: 6px 10px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 13px;
    background: #fff;
    cursor: pointer;
}}
.control-group select:focus {{
    outline: none;
    border-color: #1B2A4A;
    box-shadow: 0 0 0 2px rgba(27,42,74,0.15);
}}

/* Radio-style toggle buttons */
.toggle-group {{
    display: flex;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    overflow: hidden;
}}
.toggle-group input[type="radio"] {{ display: none; }}
.toggle-group label.toggle-btn {{
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    background: #fff;
    color: #374151;
    border-right: 1px solid #d1d5db;
    transition: all 0.15s;
    text-transform: none;
    letter-spacing: 0;
    white-space: nowrap;
}}
.toggle-group label.toggle-btn:last-child {{ border-right: none; }}
.toggle-group input[type="radio"]:checked + label.toggle-btn {{
    background: #1B2A4A;
    color: #fff;
}}

/* ── MAIN CONTAINER ─────────────────────────────────────────────── */
.container {{
    max-width: 1280px;
    margin: 0 auto;
    padding: 24px 32px;
}}

/* ── SUMMARY CARDS ──────────────────────────────────────────────── */
.cards {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 28px;
}}
.card {{
    background: #fff;
    border-radius: 10px;
    padding: 18px 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    border: 1px solid #e5e7eb;
}}
.card .card-label {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #6b7280;
    margin-bottom: 6px;
    font-weight: 600;
}}
.card .card-value {{
    font-size: 28px;
    font-weight: 700;
    color: #1B2A4A;
}}
.card .card-detail {{
    font-size: 12px;
    color: #6b7280;
    margin-top: 4px;
}}
.card .positive {{ color: #059669; }}
.card .negative {{ color: #dc2626; }}

/* ── SECTION ────────────────────────────────────────────────────── */
.section {{
    background: #fff;
    border-radius: 10px;
    padding: 20px 24px;
    margin-bottom: 24px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    border: 1px solid #e5e7eb;
}}
.section h2 {{
    font-size: 16px;
    font-weight: 700;
    color: #1B2A4A;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 2px solid #E8A630;
}}

/* ── TABLES ─────────────────────────────────────────────────────── */
table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}}
th {{
    text-align: left;
    padding: 10px 12px;
    background: #f8fafc;
    border-bottom: 2px solid #e2e8f0;
    font-weight: 600;
    color: #475569;
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
}}
th:hover {{ background: #edf2f7; }}
th.sorted-asc::after {{ content: " \\25B2"; font-size: 10px; }}
th.sorted-desc::after {{ content: " \\25BC"; font-size: 10px; }}
td {{
    padding: 8px 12px;
    border-bottom: 1px solid #f1f5f9;
}}
tr:hover td {{ background: #f8fafc; }}
tr.highlight td {{
    background: #fdf6ea;
    font-weight: 600;
}}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
th.num {{ text-align: right; }}

/* ── CHART CONTAINER ────────────────────────────────────────────── */
.chart-wrap {{
    position: relative;
    width: 100%;
    max-height: 420px;
    margin-bottom: 16px;
}}
.chart-wrap canvas {{
    width: 100% !important;
}}

/* ── COLLAPSIBLE ────────────────────────────────────────────────── */
.collapsible-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    cursor: pointer;
    padding-bottom: 8px;
    border-bottom: 2px solid #E8A630;
    margin-bottom: 16px;
}}
.collapsible-header h2 {{ border: none; margin: 0; padding: 0; }}
.collapsible-header .toggle-icon {{
    font-size: 18px;
    color: #6b7280;
    transition: transform 0.2s;
}}
.collapsible-header.open .toggle-icon {{ transform: rotate(180deg); }}
.collapsible-body {{ display: none; }}
.collapsible-body.open {{ display: block; }}

/* ── SEARCH BOX ─────────────────────────────────────────────────── */
.search-row {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
}}
.search-box {{
    padding: 7px 12px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 13px;
    width: 260px;
}}
.search-box:focus {{
    outline: none;
    border-color: #1B2A4A;
    box-shadow: 0 0 0 2px rgba(27,42,74,0.15);
}}
.btn {{
    padding: 7px 16px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    background: #fff;
    font-size: 12px;
    cursor: pointer;
    font-weight: 500;
    transition: all 0.15s;
}}
.btn:hover {{ background: #f3f4f6; }}
.btn-primary {{
    background: #1B2A4A;
    color: #fff;
    border-color: #1B2A4A;
}}
.btn-primary:hover {{ background: #152238; }}
.row-count {{
    font-size: 12px;
    color: #6b7280;
}}

/* ── RESPONSIVE ─────────────────────────────────────────────────── */
@media (max-width: 1024px) {{
    .cards {{ grid-template-columns: repeat(2, 1fr); }}
    .controls {{ padding: 10px 16px; gap: 12px; }}
    .container {{ padding: 16px; }}
}}
@media (max-width: 640px) {{
    .cards {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>

<!-- ── RAINBOW STRIPE ────────────────────────────────────────────── -->
<div class="rainbow-stripe"></div>

<!-- ── HEADER ────────────────────────────────────────────────────── -->
<div class="header">
    <img class="logo" src="{LOGO_DATA_URI}" alt="Scott Wiener for Congress">
    <div class="subtitle">CD-11 Voter Turnout Model</div>
</div>

<!-- ── CONTROLS ──────────────────────────────────────────────────── -->
<div class="controls">
    <div class="control-group">
        <label>Election</label>
        <div class="toggle-group">
            <input type="radio" name="election" id="el_primary" value="primary" checked>
            <label class="toggle-btn" for="el_primary">Primary</label>
            <input type="radio" name="election" id="el_general" value="general">
            <label class="toggle-btn" for="el_general">General</label>
        </div>
    </div>
    <div class="control-group">
        <label>Scenario</label>
        <div class="toggle-group">
            <input type="radio" name="scenario" id="sc_low" value="LOW">
            <label class="toggle-btn" for="sc_low">Low</label>
            <input type="radio" name="scenario" id="sc_expected" value="EXPECTED" checked>
            <label class="toggle-btn" for="sc_expected">Expected</label>
            <input type="radio" name="scenario" id="sc_high" value="HIGH">
            <label class="toggle-btn" for="sc_high">High</label>
        </div>
    </div>
    <div class="control-group">
        <label>Geography</label>
        <select id="geo_select">
            <option value="Citywide">Citywide</option>
            <option value="CD11">CD11</option>
            <option value="Sup_01">Sup District 1</option>
            <option value="Sup_02">Sup District 2</option>
            <option value="Sup_03">Sup District 3</option>
            <option value="Sup_04">Sup District 4</option>
            <option value="Sup_05">Sup District 5</option>
            <option value="Sup_06">Sup District 6</option>
            <option value="Sup_07">Sup District 7</option>
            <option value="Sup_08">Sup District 8</option>
            <option value="Sup_09">Sup District 9</option>
            <option value="Sup_10">Sup District 10</option>
            <option value="Sup_11">Sup District 11</option>
        </select>
    </div>
    <div class="control-group">
        <label>Demographic</label>
        <div class="toggle-group">
            <input type="radio" name="demo" id="demo_party" value="party" checked>
            <label class="toggle-btn" for="demo_party">Party</label>
            <input type="radio" name="demo" id="demo_age" value="age">
            <label class="toggle-btn" for="demo_age">Age</label>
            <input type="radio" name="demo" id="demo_race" value="race">
            <label class="toggle-btn" for="demo_race">Race</label>
        </div>
    </div>
</div>

<!-- ── MAIN CONTENT ──────────────────────────────────────────────── -->
<div class="container">

    <!-- Summary Cards -->
    <div class="cards">
        <div class="card">
            <div class="card-label">Registered Voters</div>
            <div class="card-value" id="card_registered">--</div>
            <div class="card-detail" id="card_registered_detail"></div>
        </div>
        <div class="card">
            <div class="card-label">Estimated Ballots</div>
            <div class="card-value" id="card_ballots">--</div>
            <div class="card-detail" id="card_ballots_detail"></div>
        </div>
        <div class="card">
            <div class="card-label">Estimated Turnout</div>
            <div class="card-value" id="card_turnout">--</div>
            <div class="card-detail" id="card_turnout_detail"></div>
        </div>
        <div class="card">
            <div class="card-label" id="card_hist_label">vs. Historical</div>
            <div class="card-value" id="card_hist_value">--</div>
            <div class="card-detail" id="card_hist_detail"></div>
        </div>
    </div>

    <!-- Scenario Comparison -->
    <div class="section">
        <h2>Scenario Comparison</h2>
        <table id="scenario_table">
            <thead>
                <tr>
                    <th>Scenario</th>
                    <th class="num">Registered</th>
                    <th class="num">Est. Ballots</th>
                    <th class="num">Turnout %</th>
                    <th class="num">vs Jun 2018</th>
                    <th class="num">vs Jun 2022</th>
                    <th class="num">vs Mar 2024</th>
                    <th class="num">vs Nov 2018</th>
                    <th class="num">vs Nov 2022</th>
                    <th class="num">vs Nov 2024</th>
                </tr>
            </thead>
            <tbody id="scenario_tbody"></tbody>
        </table>
    </div>

    <!-- Demographic Breakdown Chart -->
    <div class="section">
        <h2 id="demo_chart_title">Demographic Breakdown</h2>
        <div class="chart-wrap">
            <canvas id="demo_chart"></canvas>
        </div>
    </div>

    <!-- Demographic Table -->
    <div class="section">
        <h2 id="demo_table_title">Demographic Detail</h2>
        <table id="demo_table">
            <thead>
                <tr>
                    <th data-col="group">Group</th>
                    <th class="num" data-col="registered">Registered</th>
                    <th class="num" data-col="ballots">Est. Ballots</th>
                    <th class="num" data-col="turnout">Turnout %</th>
                    <th class="num" data-col="share">Share of Electorate</th>
                </tr>
            </thead>
            <tbody id="demo_tbody"></tbody>
        </table>
    </div>

    <!-- Supervisor District Comparison -->
    <div class="section" id="sup_section">
        <h2>Supervisor District Comparison</h2>
        <div class="chart-wrap">
            <canvas id="sup_chart"></canvas>
        </div>
        <table id="sup_table">
            <thead>
                <tr>
                    <th data-col="district">District</th>
                    <th class="num" data-col="registered">Registered</th>
                    <th class="num" data-col="ballots">Est. Ballots</th>
                    <th class="num" data-col="turnout">Turnout %</th>
                </tr>
            </thead>
            <tbody id="sup_tbody"></tbody>
        </table>
    </div>

    <!-- Precinct Detail Panel -->
    <div class="section">
        <div class="collapsible-header" id="precinct_header" onclick="togglePrecinct()">
            <h2>Precinct Detail</h2>
            <span class="toggle-icon">&#9660;</span>
        </div>
        <div class="collapsible-body" id="precinct_body">
            <div class="search-row">
                <input type="text" class="search-box" id="precinct_search"
                       placeholder="Search by precinct or district...">
                <button class="btn" id="btn_show_all" onclick="toggleShowAll()">Show All</button>
                <span class="row-count" id="precinct_count"></span>
            </div>
            <table id="precinct_table">
                <thead>
                    <tr>
                        <th data-col="precinct">Precinct</th>
                        <th data-col="district">Sup District</th>
                        <th class="num" data-col="registered">Registered</th>
                        <th class="num" data-col="ballots">Est. Ballots</th>
                        <th class="num" data-col="turnout">Turnout %</th>
                    </tr>
                </thead>
                <tbody id="precinct_tbody"></tbody>
            </table>
        </div>
    </div>

</div><!-- /.container -->

<!-- ── EMBEDDED DATA ─────────────────────────────────────────────── -->
<script>
const GEO_DATA = {geo_json};
const GEO_DEMO_DATA = {geo_demo_json};
const PRECINCT_DATA = {precinct_json};
const DEMO_DATA = {demo_json};
</script>

<!-- ── DASHBOARD LOGIC ───────────────────────────────────────────── -->
<script>
// ── State ──────────────────────────────────────────────────────────
let state = {{
    election: 'primary',
    scenario: 'EXPECTED',
    geography: 'Citywide',
    demoDimension: 'party',
    precinctShowAll: false,
    precinctSearch: '',
    sortCol: null,
    sortDir: 'asc',
    demoSortCol: null,
    demoSortDir: 'asc',
    supSortCol: null,
    supSortDir: 'asc',
    precinctSortCol: null,
    precinctSortDir: 'asc',
}};

let demoChart = null;
let supChart = null;

// ── Utility ────────────────────────────────────────────────────────
function fmt(n) {{
    if (n == null || isNaN(n)) return '--';
    return Math.round(n).toLocaleString();
}}
function fmtPct(n) {{
    if (n == null || isNaN(n)) return '--';
    return (n * 100).toFixed(1) + '%';
}}
function fmtDelta(n) {{
    if (n == null || isNaN(n)) return '--';
    const v = (n * 100).toFixed(1);
    const sign = n >= 0 ? '+' : '';
    return sign + v + ' pp';
}}
function deltaClass(n) {{
    if (n == null || isNaN(n)) return '';
    return n >= 0 ? 'positive' : 'negative';
}}

// Color palette
const COLORS = {{
    party: {{
        'Democrat':  '#2563eb',
        'Republican': '#dc2626',
        'NPP':       '#8b5cf6',
        'Other':     '#6b7280',
    }},
    age: {{
        '18-29': '#06b6d4',
        '30-44': '#3b82f6',
        '45-64': '#8b5cf6',
        '65+':   '#f59e0b',
    }},
    race: {{
        'Asian':           '#0891b2',
        'Black':           '#7c3aed',
        'Latino/Hispanic': '#d97706',
        'White':           '#2563eb',
        'Other/Unknown':   '#6b7280',
    }},
}};

const SUP_COLORS = [
    '#2563eb', '#0891b2', '#059669', '#d97706', '#dc2626',
    '#7c3aed', '#db2777', '#84cc16', '#f59e0b', '#6366f1', '#475569'
];

// ── Data Lookups ───────────────────────────────────────────────────
function getGeoRow(geo, election, scenario) {{
    return GEO_DATA.find(r =>
        r.geography === geo &&
        r.election_type === election &&
        r.scenario === scenario
    );
}}

function getGeoRows(geo, election) {{
    return GEO_DATA.filter(r =>
        r.geography === geo &&
        r.election_type === election
    );
}}

function getGeoDemoRows(geo, election, scenario, dimension) {{
    return GEO_DEMO_DATA.filter(r =>
        r.geography === geo &&
        r.election_type === election &&
        r.scenario === scenario &&
        r.dimension === dimension
    );
}}

function getSupRows(election, scenario) {{
    return GEO_DATA.filter(r =>
        r.election_type === election &&
        r.scenario === scenario &&
        r.geography.startsWith('Sup_')
    ).sort((a, b) => a.geography.localeCompare(b.geography));
}}

function getPrecinctRows(election, scenario, geography) {{
    let rows = PRECINCT_DATA.filter(r =>
        r.election_type === election &&
        r.scenario === scenario
    );
    if (geography === 'CD11') {{
        rows = rows.filter(r => r.in_cd11 === true || r.in_cd11 === 'True');
    }} else if (geography.startsWith('Sup_')) {{
        const dist = parseInt(geography.replace('Sup_', ''));
        rows = rows.filter(r => r.sup_district === dist);
    }}
    return rows;
}}

// ── Control Bindings ───────────────────────────────────────────────
document.querySelectorAll('input[name="election"]').forEach(el => {{
    el.addEventListener('change', e => {{
        state.election = e.target.value;
        update();
    }});
}});
document.querySelectorAll('input[name="scenario"]').forEach(el => {{
    el.addEventListener('change', e => {{
        state.scenario = e.target.value;
        update();
    }});
}});
document.getElementById('geo_select').addEventListener('change', e => {{
    state.geography = e.target.value;
    update();
}});
document.querySelectorAll('input[name="demo"]').forEach(el => {{
    el.addEventListener('change', e => {{
        state.demoDimension = e.target.value;
        update();
    }});
}});
document.getElementById('precinct_search').addEventListener('input', e => {{
    state.precinctSearch = e.target.value.toLowerCase();
    renderPrecinctTable();
}});

function togglePrecinct() {{
    const header = document.getElementById('precinct_header');
    const body = document.getElementById('precinct_body');
    header.classList.toggle('open');
    body.classList.toggle('open');
}}

function toggleShowAll() {{
    state.precinctShowAll = !state.precinctShowAll;
    const btn = document.getElementById('btn_show_all');
    btn.textContent = state.precinctShowAll ? 'Show First 50' : 'Show All';
    renderPrecinctTable();
}}

// ── Sortable Tables ────────────────────────────────────────────────
function attachSort(tableId, stateKey, renderFn) {{
    document.querySelectorAll('#' + tableId + ' th[data-col]').forEach(th => {{
        th.addEventListener('click', () => {{
            const col = th.dataset.col;
            if (state[stateKey + 'SortCol'] === col) {{
                state[stateKey + 'SortDir'] = state[stateKey + 'SortDir'] === 'asc' ? 'desc' : 'asc';
            }} else {{
                state[stateKey + 'SortCol'] = col;
                state[stateKey + 'SortDir'] = 'asc';
            }}
            renderFn();
        }});
    }});
}}

function sortRows(rows, col, dir, mapping) {{
    if (!col) return rows;
    const key = mapping[col] || col;
    return [...rows].sort((a, b) => {{
        let va = a[key], vb = b[key];
        if (typeof va === 'string') {{
            return dir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
        }}
        va = va ?? -Infinity;
        vb = vb ?? -Infinity;
        return dir === 'asc' ? va - vb : vb - va;
    }});
}}

function updateSortIndicators(tableId, stateKey) {{
    document.querySelectorAll('#' + tableId + ' th').forEach(th => {{
        th.classList.remove('sorted-asc', 'sorted-desc');
        if (th.dataset.col === state[stateKey + 'SortCol']) {{
            th.classList.add('sorted-' + state[stateKey + 'SortDir']);
        }}
    }});
}}

// ── Render: Summary Cards ──────────────────────────────────────────
function renderCards() {{
    const row = getGeoRow(state.geography, state.election, state.scenario);
    if (!row) return;

    document.getElementById('card_registered').textContent = fmt(row.registered_voters);
    document.getElementById('card_registered_detail').textContent =
        state.geography === 'Citywide' ? 'All SF precincts' :
        state.geography === 'CD11' ? 'CD-11 precincts (excl. Sup D11)' :
        'Supervisor District ' + state.geography.replace('Sup_', '');

    document.getElementById('card_ballots').textContent = fmt(row.estimated_ballots);
    document.getElementById('card_ballots_detail').textContent = state.scenario + ' scenario';

    document.getElementById('card_turnout').textContent = fmtPct(row.estimated_turnout_pct);
    document.getElementById('card_turnout_detail').textContent =
        state.election === 'primary' ? 'June 2026 Primary' : 'November 2026 General';

    // vs Historical: primary -> vs Mar 2024, general -> vs Nov 2022
    let histDelta, histLabel;
    if (state.election === 'primary') {{
        histDelta = row.vs_mar2024;
        histLabel = 'vs. March 2024 Primary';
    }} else {{
        histDelta = row.vs_nov2022;
        histLabel = 'vs. November 2022 General';
    }}
    document.getElementById('card_hist_label').textContent = histLabel;
    const histEl = document.getElementById('card_hist_value');
    histEl.textContent = fmtDelta(histDelta);
    histEl.className = 'card-value ' + deltaClass(histDelta);

    // Show 2018 wave comparison as secondary detail
    const detailDelta = state.election === 'primary' ? row.vs_jun2018 : row.vs_nov2018;
    const detailLabel = state.election === 'primary' ? 'vs Jun 2018 (wave)' : 'vs Nov 2018 (wave)';
    const detailEl = document.getElementById('card_hist_detail');
    detailEl.innerHTML = detailLabel + ': <span class="' + deltaClass(detailDelta) + '">' + fmtDelta(detailDelta) + '</span>';
}}

// ── Render: Scenario Table ─────────────────────────────────────────
function renderScenarioTable() {{
    const rows = getGeoRows(state.geography, state.election);
    const order = ['HIGH', 'EXPECTED', 'LOW'];
    const tbody = document.getElementById('scenario_tbody');
    tbody.innerHTML = '';

    order.forEach(sc => {{
        const row = rows.find(r => r.scenario === sc);
        if (!row) return;
        const tr = document.createElement('tr');
        if (sc === state.scenario) tr.className = 'highlight';
        tr.innerHTML = `
            <td>${{sc}}</td>
            <td class="num">${{fmt(row.registered_voters)}}</td>
            <td class="num">${{fmt(row.estimated_ballots)}}</td>
            <td class="num">${{fmtPct(row.estimated_turnout_pct)}}</td>
            <td class="num ${{deltaClass(row.vs_jun2018)}}">${{fmtDelta(row.vs_jun2018)}}</td>
            <td class="num ${{deltaClass(row.vs_jun2022)}}">${{fmtDelta(row.vs_jun2022)}}</td>
            <td class="num ${{deltaClass(row.vs_mar2024)}}">${{fmtDelta(row.vs_mar2024)}}</td>
            <td class="num ${{deltaClass(row.vs_nov2018)}}">${{fmtDelta(row.vs_nov2018)}}</td>
            <td class="num ${{deltaClass(row.vs_nov2022)}}">${{fmtDelta(row.vs_nov2022)}}</td>
            <td class="num ${{deltaClass(row.vs_nov2024)}}">${{fmtDelta(row.vs_nov2024)}}</td>
        `;
        tbody.appendChild(tr);
    }});
}}

// ── Render: Demographic Chart ──────────────────────────────────────
function renderDemoChart() {{
    const dim = state.demoDimension;
    const demoRows = getGeoDemoRows(state.geography, state.election, state.scenario, dim);
    if (!demoRows.length) return;

    const dimLabel = dim.charAt(0).toUpperCase() + dim.slice(1);
    document.getElementById('demo_chart_title').textContent =
        'Estimated Turnout by ' + dimLabel;

    const labels = demoRows.map(r => r.group);
    const values = demoRows.map(r => r.estimated_turnout_pct * 100);
    const colors = labels.map(l => (COLORS[dim] && COLORS[dim][l]) || '#6b7280');

    if (demoChart) demoChart.destroy();

    const ctx = document.getElementById('demo_chart').getContext('2d');
    demoChart = new Chart(ctx, {{
        type: 'bar',
        data: {{
            labels: labels,
            datasets: [{{
                label: 'Turnout %',
                data: values,
                backgroundColor: colors,
                borderColor: colors.map(c => c),
                borderWidth: 1,
                borderRadius: 4,
            }}]
        }},
        options: {{
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{
                legend: {{ display: false }},
                tooltip: {{
                    callbacks: {{
                        label: function(ctx) {{
                            const row = demoRows[ctx.dataIndex];
                            return [
                                'Turnout: ' + ctx.parsed.x.toFixed(1) + '%',
                                'Registered: ' + fmt(row.registered_in_group),
                                'Est. Ballots: ' + fmt(row.estimated_ballots),
                            ];
                        }}
                    }}
                }}
            }},
            scales: {{
                x: {{
                    beginAtZero: true,
                    max: 100,
                    ticks: {{ callback: v => v + '%' }},
                    grid: {{ color: '#f1f5f9' }},
                }},
                y: {{
                    grid: {{ display: false }},
                }}
            }}
        }}
    }});
}}

// ── Render: Demographic Table ──────────────────────────────────────
function renderDemoTable() {{
    const dim = state.demoDimension;
    const dimLabel = dim.charAt(0).toUpperCase() + dim.slice(1);
    document.getElementById('demo_table_title').textContent =
        dimLabel + ' Group Detail';

    let demoRows = getGeoDemoRows(state.geography, state.election, state.scenario, dim);

    const mapping = {{
        group: 'group',
        registered: 'registered_in_group',
        ballots: 'estimated_ballots',
        turnout: 'estimated_turnout_pct',
        share: 'pct_of_geography',
    }};
    demoRows = sortRows(demoRows, state.demoSortCol, state.demoSortDir, mapping);
    updateSortIndicators('demo_table', 'demo');

    const tbody = document.getElementById('demo_tbody');
    tbody.innerHTML = '';

    demoRows.forEach(r => {{
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${{r.group}}</td>
            <td class="num">${{fmt(r.registered_in_group)}}</td>
            <td class="num">${{fmt(r.estimated_ballots)}}</td>
            <td class="num">${{fmtPct(r.estimated_turnout_pct)}}</td>
            <td class="num">${{fmtPct(r.pct_of_geography)}}</td>
        `;
        tbody.appendChild(tr);
    }});
}}

// ── Render: Supervisor District Section ────────────────────────────
function renderSupSection() {{
    const section = document.getElementById('sup_section');
    const geo = state.geography;
    // Show only for Citywide or CD11
    if (geo !== 'Citywide' && geo !== 'CD11') {{
        section.style.display = 'none';
        return;
    }}
    section.style.display = '';

    let supRows = getSupRows(state.election, state.scenario);
    if (geo === 'CD11') {{
        supRows = supRows.filter(r => r.geography !== 'Sup_11');
    }}

    // Chart
    const labels = supRows.map(r => 'D' + parseInt(r.geography.replace('Sup_', '')));
    const values = supRows.map(r => r.estimated_turnout_pct * 100);
    const bgColors = supRows.map((_, i) => SUP_COLORS[i % SUP_COLORS.length]);

    if (supChart) supChart.destroy();

    const ctx = document.getElementById('sup_chart').getContext('2d');
    supChart = new Chart(ctx, {{
        type: 'bar',
        data: {{
            labels: labels,
            datasets: [{{
                label: 'Turnout %',
                data: values,
                backgroundColor: bgColors,
                borderColor: bgColors,
                borderWidth: 1,
                borderRadius: 4,
            }}]
        }},
        options: {{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{
                legend: {{ display: false }},
                tooltip: {{
                    callbacks: {{
                        label: function(ctx) {{
                            const row = supRows[ctx.dataIndex];
                            return [
                                'Turnout: ' + ctx.parsed.y.toFixed(1) + '%',
                                'Registered: ' + fmt(row.registered_voters),
                                'Est. Ballots: ' + fmt(row.estimated_ballots),
                            ];
                        }}
                    }}
                }}
            }},
            scales: {{
                y: {{
                    beginAtZero: true,
                    max: 100,
                    ticks: {{ callback: v => v + '%' }},
                    grid: {{ color: '#f1f5f9' }},
                }},
                x: {{
                    grid: {{ display: false }},
                }}
            }}
        }}
    }});

    // Table
    const sortMapping = {{
        district: 'geography',
        registered: 'registered_voters',
        ballots: 'estimated_ballots',
        turnout: 'estimated_turnout_pct',
    }};
    let sorted = sortRows(supRows, state.supSortCol, state.supSortDir, sortMapping);
    updateSortIndicators('sup_table', 'sup');

    const tbody = document.getElementById('sup_tbody');
    tbody.innerHTML = '';

    sorted.forEach(r => {{
        const dist = parseInt(r.geography.replace('Sup_', ''));
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>District ${{dist}}</td>
            <td class="num">${{fmt(r.registered_voters)}}</td>
            <td class="num">${{fmt(r.estimated_ballots)}}</td>
            <td class="num">${{fmtPct(r.estimated_turnout_pct)}}</td>
        `;
        tbody.appendChild(tr);
    }});
}}

// ── Render: Precinct Table ─────────────────────────────────────────
function renderPrecinctTable() {{
    let rows = getPrecinctRows(state.election, state.scenario, state.geography);

    // Search filter
    if (state.precinctSearch) {{
        const q = state.precinctSearch;
        rows = rows.filter(r =>
            String(r.PrecinctName).toLowerCase().includes(q) ||
            String(r.sup_district).includes(q)
        );
    }}

    // Sort
    const mapping = {{
        precinct: 'PrecinctName',
        district: 'sup_district',
        registered: 'registered_voters',
        ballots: 'estimated_ballots',
        turnout: 'estimated_turnout_pct',
    }};
    rows = sortRows(rows, state.precinctSortCol, state.precinctSortDir, mapping);
    updateSortIndicators('precinct_table', 'precinct');

    const total = rows.length;
    const display = state.precinctShowAll ? rows : rows.slice(0, 50);

    document.getElementById('precinct_count').textContent =
        'Showing ' + display.length + ' of ' + total + ' precincts';

    const tbody = document.getElementById('precinct_tbody');
    tbody.innerHTML = '';

    display.forEach(r => {{
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${{r.PrecinctName}}</td>
            <td class="num">${{r.sup_district}}</td>
            <td class="num">${{fmt(r.registered_voters)}}</td>
            <td class="num">${{fmt(r.estimated_ballots)}}</td>
            <td class="num">${{fmtPct(r.estimated_turnout_pct)}}</td>
        `;
        tbody.appendChild(tr);
    }});
}}

// ── Master Update ──────────────────────────────────────────────────
function update() {{
    renderCards();
    renderScenarioTable();
    renderDemoChart();
    renderDemoTable();
    renderSupSection();
    renderPrecinctTable();
}}

// ── Attach Sort Handlers ───────────────────────────────────────────
attachSort('demo_table', 'demo', renderDemoTable);
attachSort('sup_table', 'sup', renderSupSection);
attachSort('precinct_table', 'precinct', renderPrecinctTable);

// ── Initial Render ─────────────────────────────────────────────────
update();
</script>

<!-- ── FOOTER ───────────────────────────────────────────────────── -->
<div class="rainbow-stripe" style="margin-top: 24px;"></div>
<div style="background: #1B2A4A; color: rgba(255,255,255,0.5); text-align: center; padding: 16px; font-size: 11px;">
    Paid for by Scott Wiener for Congress &mdash; Internal Use Only &mdash; Confidential
</div>
</body>
</html>"""

# ── WRITE OUTPUT ──────────────────────────────────────────────────────────────
print(f"\nWriting dashboard to {OUTPUT_FILE}...")
os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(html)

file_size = os.path.getsize(OUTPUT_FILE)

print(f"\n{'=' * 70}")
print(f"DASHBOARD GENERATED SUCCESSFULLY")
print(f"{'=' * 70}")
print(f"  Output: {OUTPUT_FILE}")
print(f"  Size:   {file_size:,} bytes ({file_size / 1024:.1f} KB)")
print(f"\n  Open in your browser:")
print(f"  file://{OUTPUT_FILE}")
print(f"{'=' * 70}")
