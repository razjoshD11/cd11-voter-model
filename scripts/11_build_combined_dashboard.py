#!/usr/bin/env python3
"""
11_build_combined_dashboard.py

Takes the original turnout dashboard and adds:
  - Support & Universes content (charts + tables)
  - Interactive Leaflet choropleth map
Produces a single unified HTML file.
"""

import json
import os
import re
import sys

import numpy as np
import pandas as pd

# ── Paths ────────────────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIG_HTML   = os.path.join(BASE, "dashboard", "turnout_dashboard.html")
VOTER_CSV   = os.path.join(BASE, "data", "processed", "cd11_voters_with_scores.csv")
GEOJSON     = os.path.join(BASE, "data", "geo", "sf_precincts.geojson")
OUT_HTML    = os.path.join(BASE, "dashboard", "turnout_dashboard_v2.html")

# ── 1. Read original HTML ────────────────────────────────────────────────────
print("[1/10] Reading original dashboard ...")
with open(ORIG_HTML, "r", encoding="utf-8") as f:
    html = f.read()
print(f"       {len(html):,} characters, {html.count(chr(10))+1} lines")

# ── 2. Rebrand colors & fonts ───────────────────────────────────────────────
print("[2/10] Rebranding colors and fonts ...")

# Color replacements (case-insensitive for hex codes)
html = re.sub(r'#1[Bb]2[Aa]4[Aa]', '#191a4d', html)
html = re.sub(r'#[Ee]8[Aa]630', '#f89828', html)
html = html.replace('rgba(27,42,74', 'rgba(25,26,77')
html = html.replace('rgba(27, 42, 74', 'rgba(25, 26, 77')

# Font replacement
html = re.sub(
    r'<link[^>]*googleapis\.com/css2\?family=Montserrat[^>]*>',
    '<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;600;700;800'
    '&family=Besley:wght@400;600;700&family=Barlow+Condensed:wght@400;600;700&display=swap" rel="stylesheet">',
    html
)
html = html.replace("'Montserrat'", "'Barlow'")

# Title update
html = html.replace(
    'CD-11 Voter Turnout Model',
    'CD-11 Voter Targeting Dashboard'
)

# ── 3. Add Leaflet CDN before </head> ────────────────────────────────────────
print("[3/10] Adding Leaflet CDN ...")
leaflet_cdn = (
    '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />\n'
    '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>\n'
)
html = html.replace('</head>', leaflet_cdn + '</head>')

# ── 4. Aggregate voter data ─────────────────────────────────────────────────
print("[4/10] Reading and aggregating voter data ...")
df = pd.read_csv(VOTER_CSV, low_memory=False)
print(f"       {len(df):,} voters loaded")

# Clean PrecinctName to string (4-digit where possible)
df['prec_str'] = df['PrecinctName'].astype(str).str.replace(r'\.0$', '', regex=True)

# Ensure boolean columns
for col in ['base_dropoff', 'persuasion_priority', 'is_maga', 'is_saikat_likely', 'is_conservative_opp']:
    df[col] = df[col].astype(bool)

# Supervisor district from HD column (which has assembly districts)
# The voter file uses CountySupervisorName for supervisor districts.
# Extract district number from CountySupervisorName or use HD-based mapping.
# Let's check what we have:
if 'CountySupervisorName' in df.columns:
    # Extract district number: e.g., "District 1 - ..." -> 1
    df['district'] = df['CountySupervisorName'].astype(str).str.extract(r'(\d+)')[0]
    df['district'] = pd.to_numeric(df['district'], errors='coerce')
else:
    df['district'] = np.nan

# Age groups
def age_bucket(age):
    if pd.isna(age):
        return 'Unknown'
    age = int(age)
    if age < 30:
        return '18-29'
    elif age < 45:
        return '30-44'
    elif age < 65:
        return '45-64'
    else:
        return '65+'
df['age_group'] = df['Age'].apply(age_bucket)

# 4A: Score distribution histogram (bins of 5)
bins = list(range(0, 101, 5))
bin_labels = [f"{b}-{b+4}" for b in bins[:-1]]
df['score_bin'] = pd.cut(df['support_score'], bins=bins, right=False, labels=bin_labels)
score_hist = df['score_bin'].value_counts().sort_index().to_dict()
# Ensure all bins present
score_histogram = []
for lbl in bin_labels:
    score_histogram.append({
        'label': lbl,
        'count': int(score_hist.get(lbl, 0))
    })

# 4B: District-level summaries
print("       Computing district summaries ...")
district_summaries = []
for dist in sorted(df['district'].dropna().unique()):
    sub = df[df['district'] == dist]
    total = len(sub)
    if total == 0:
        continue
    base_ct = int((sub['universe'] == 'Base').sum())
    pers_ct = int((sub['universe'] == 'Persuasion').sum())
    opp_ct  = int((sub['universe'] == 'Opposition').sum())
    district_summaries.append({
        'district': int(dist),
        'total_voters': total,
        'base_count': base_ct,
        'persuasion_count': pers_ct,
        'opposition_count': opp_ct,
        'base_pct': round(base_ct / total * 100, 1),
        'persuasion_pct': round(pers_ct / total * 100, 1),
        'opposition_pct': round(opp_ct / total * 100, 1),
        'mean_score': round(float(sub['support_score'].mean()), 1),
        'mean_turnout': round(float(sub['turnout_probability'].mean()), 1),
        'base_dropoff_count': int(sub['base_dropoff'].sum()),
        'maga_count': int(sub['is_maga'].sum()),
        'saikat_count': int(sub['is_saikat_likely'].sum()),
    })

# 4C: Demographic breakdowns
print("       Computing demographic breakdowns ...")
demo_breakdowns = {}

# Party
party_data = []
for party, grp in df.groupby('Party'):
    total = len(grp)
    party_data.append({
        'group': str(party),
        'total': total,
        'base_count': int((grp['universe'] == 'Base').sum()),
        'persuasion_count': int((grp['universe'] == 'Persuasion').sum()),
        'opposition_count': int((grp['universe'] == 'Opposition').sum()),
        'base_pct': round((grp['universe'] == 'Base').sum() / total * 100, 1),
    })
party_data = [d for d in party_data if d['total'] >= 10]
party_data.sort(key=lambda x: x['total'], reverse=True)
demo_breakdowns['party'] = party_data

# Race
race_data = []
for race, grp in df.groupby('RaceName'):
    total = len(grp)
    race_data.append({
        'group': str(race),
        'total': total,
        'base_count': int((grp['universe'] == 'Base').sum()),
        'persuasion_count': int((grp['universe'] == 'Persuasion').sum()),
        'opposition_count': int((grp['universe'] == 'Opposition').sum()),
        'base_pct': round((grp['universe'] == 'Base').sum() / total * 100, 1),
    })
race_data = [d for d in race_data if d['total'] >= 10]
race_data.sort(key=lambda x: x['total'], reverse=True)
demo_breakdowns['race'] = race_data

# Age
age_data = []
for ag, grp in df.groupby('age_group'):
    total = len(grp)
    age_data.append({
        'group': str(ag),
        'total': total,
        'base_count': int((grp['universe'] == 'Base').sum()),
        'persuasion_count': int((grp['universe'] == 'Persuasion').sum()),
        'opposition_count': int((grp['universe'] == 'Opposition').sum()),
        'base_pct': round((grp['universe'] == 'Base').sum() / total * 100, 1),
    })
# Sort by age group order
age_data = [d for d in age_data if d['total'] >= 10]
age_order = {'18-29': 0, '30-44': 1, '45-64': 2, '65+': 3, 'Unknown': 4}
age_data.sort(key=lambda x: age_order.get(x['group'], 99))
demo_breakdowns['age'] = age_data

# 4D: Opposition breakdown
print("       Computing opposition breakdown ...")
opp_counts = df[df['universe'] == 'Opposition']['opposition_type'].value_counts().to_dict()
opposition_breakdown = []
total_opp = sum(opp_counts.values())
for otype, cnt in sorted(opp_counts.items(), key=lambda x: -x[1]):
    if cnt >= 10:
        opposition_breakdown.append({
            'type': str(otype),
            'count': int(cnt),
            'pct': round(cnt / total_opp * 100, 1) if total_opp > 0 else 0,
        })

# 4E: Persuasion priority breakdown
print("       Computing persuasion priorities ...")
pers_df = df[df['persuasion_priority'] == True].copy()
persuasion_segments = []

# By age group
for ag, grp in pers_df.groupby('age_group'):
    if len(grp) >= 5000:
        persuasion_segments.append({
            'segment': f'Age: {ag}',
            'count': len(grp),
            'mean_score': round(float(grp['support_score'].mean()), 1),
        })

# By race
for race, grp in pers_df.groupby('RaceName'):
    if len(grp) >= 5000:
        persuasion_segments.append({
            'segment': f'Race: {race}',
            'count': len(grp),
            'mean_score': round(float(grp['support_score'].mean()), 1),
        })

# By district
for dist, grp in pers_df.groupby('district'):
    if pd.notna(dist) and len(grp) >= 5000:
        persuasion_segments.append({
            'segment': f'District {int(dist)}',
            'count': len(grp),
            'mean_score': round(float(grp['support_score'].mean()), 1),
        })

# Sort by mean support score (likely supporter score), descending
persuasion_segments.sort(key=lambda x: -x['mean_score'])

# Overall totals
totals = {
    'total_voters': len(df),
    'base_count': int((df['universe'] == 'Base').sum()),
    'persuasion_count': int((df['universe'] == 'Persuasion').sum()),
    'opposition_count': int((df['universe'] == 'Opposition').sum()),
    'base_dropoff_count': int(df['base_dropoff'].sum()),
    'persuasion_priority_count': int(df['persuasion_priority'].sum()),
    'maga_count': int(df['is_maga'].sum()),
    'saikat_count': int(df['is_saikat_likely'].sum()),
    'mean_score': round(float(df['support_score'].mean()), 1),
    'mean_turnout': round(float(df['turnout_probability'].mean()), 1),
}

# 4F: Precinct-level aggregates
print("       Computing precinct aggregates ...")
prec_agg = df.groupby('prec_str').agg(
    voter_count=('support_score', 'size'),
    mean_support_score=('support_score', 'mean'),
    mean_turnout=('turnout_probability', 'mean'),
    base_count=('universe', lambda x: (x == 'Base').sum()),
    opposition_count=('universe', lambda x: (x == 'Opposition').sum()),
    persuasion_count=('universe', lambda x: (x == 'Persuasion').sum()),
    base_dropoff_count=('base_dropoff', 'sum'),
    maga_count=('is_maga', 'sum'),
    saikat_count=('is_saikat_likely', 'sum'),
    mean_vote_freq=('vote_frequency_score', 'mean'),
    persuasion_priority_count=('persuasion_priority', 'sum'),
).reset_index()

# Get district per precinct (mode of district for voters in each precinct)
prec_district = df.groupby('prec_str')['district'].agg(
    lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else np.nan
)
prec_agg = prec_agg.merge(prec_district.rename('district'), left_on='prec_str', right_index=True, how='left')

prec_agg['base_pct'] = (prec_agg['base_count'] / prec_agg['voter_count'] * 100).round(1)
prec_agg['opposition_pct'] = (prec_agg['opposition_count'] / prec_agg['voter_count'] * 100).round(1)
prec_agg['persuasion_pct'] = (prec_agg['persuasion_count'] / prec_agg['voter_count'] * 100).round(1)
prec_agg['base_dropoff_pct'] = (prec_agg['base_dropoff_count'] / prec_agg['voter_count'] * 100).round(1)
prec_agg['maga_pct'] = (prec_agg['maga_count'] / prec_agg['voter_count'] * 100).round(1)
prec_agg['saikat_pct'] = (prec_agg['saikat_count'] / prec_agg['voter_count'] * 100).round(1)
prec_agg['persuasion_priority_pct'] = (prec_agg['persuasion_priority_count'] / prec_agg['voter_count'] * 100).round(1)
prec_agg['mean_support_score'] = prec_agg['mean_support_score'].round(1)
prec_agg['mean_turnout'] = prec_agg['mean_turnout'].round(1)
prec_agg['mean_vote_freq'] = prec_agg['mean_vote_freq'].round(2)

# Build precinct dict
precinct_data = {}
for _, row in prec_agg.iterrows():
    precinct_data[row['prec_str']] = {
        'voter_count': int(row['voter_count']),
        'mean_support_score': float(row['mean_support_score']),
        'mean_turnout': float(row['mean_turnout']),
        'base_pct': float(row['base_pct']),
        'opposition_pct': float(row['opposition_pct']),
        'persuasion_pct': float(row['persuasion_pct']),
        'base_dropoff_pct': float(row['base_dropoff_pct']),
        'maga_pct': float(row['maga_pct']),
        'saikat_pct': float(row['saikat_pct']),
        'persuasion_priority_pct': float(row['persuasion_priority_pct']),
        'mean_vote_freq': float(row['mean_vote_freq']),
        'district': int(row['district']) if pd.notna(row.get('district')) else 0,
    }

# District-level aggregates for geography toggle
print("       Computing district & citywide map aggregates ...")
district_map_data = {}
for dist in sorted(df['district'].dropna().unique()):
    sub = df[df['district'] == dist]
    total = len(sub)
    if total == 0:
        continue
    district_map_data[str(int(dist))] = {
        'voter_count': total,
        'mean_support_score': round(float(sub['support_score'].mean()), 1),
        'mean_turnout': round(float(sub['turnout_probability'].mean()), 1),
        'base_pct': round(float((sub['universe'] == 'Base').sum() / total * 100), 1),
        'opposition_pct': round(float((sub['universe'] == 'Opposition').sum() / total * 100), 1),
        'persuasion_pct': round(float((sub['universe'] == 'Persuasion').sum() / total * 100), 1),
        'maga_pct': round(float(sub['is_maga'].sum() / total * 100), 1),
        'persuasion_priority_pct': round(float(sub['persuasion_priority'].sum() / total * 100), 1),
        'mean_vote_freq': round(float(sub['vote_frequency_score'].mean()), 1),
    }

citywide_data = {
    'voter_count': len(df),
    'mean_support_score': round(float(df['support_score'].mean()), 1),
    'mean_turnout': round(float(df['turnout_probability'].mean()), 1),
    'base_pct': round(float((df['universe'] == 'Base').sum() / len(df) * 100), 1),
    'opposition_pct': round(float((df['universe'] == 'Opposition').sum() / len(df) * 100), 1),
    'persuasion_pct': round(float((df['universe'] == 'Persuasion').sum() / len(df) * 100), 1),
    'maga_pct': round(float(df['is_maga'].sum() / len(df) * 100), 1),
    'persuasion_priority_pct': round(float(df['persuasion_priority'].sum() / len(df) * 100), 1),
    'mean_vote_freq': round(float(df['vote_frequency_score'].mean()), 1),
}

# ── 5. Load GeoJSON and merge ───────────────────────────────────────────────
print("[5/10] Loading GeoJSON ...")
geo = None
if os.path.exists(GEOJSON):
    with open(GEOJSON, "r", encoding="utf-8") as f:
        geo = json.load(f)
    matched = 0
    for feat in geo['features']:
        prec_id = str(feat['properties'].get('precinct', ''))
        if prec_id in precinct_data:
            feat['properties'].update(precinct_data[prec_id])
            matched += 1
        else:
            # Fill with zeros so the layer still renders
            feat['properties'].update({
                'voter_count': 0, 'mean_support_score': 0, 'mean_turnout': 0,
                'base_pct': 0, 'opposition_pct': 0, 'persuasion_pct': 0,
                'base_dropoff_pct': 0, 'maga_pct': 0, 'saikat_pct': 0,
                'persuasion_priority_pct': 0, 'mean_vote_freq': 0,
            })
    print(f"       Matched {matched}/{len(geo['features'])} GeoJSON features with voter data")
else:
    print("       GeoJSON not found, will attempt download ...")
    try:
        import urllib.request
        url = "https://data.sfgov.org/api/geospatial/d6x4-hefw?method=export&type=GeoJSON"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            geo = json.loads(resp.read().decode('utf-8'))
        print(f"       Downloaded {len(geo.get('features', []))} features")
        # Try matching
        matched = 0
        for feat in geo['features']:
            props = feat['properties']
            prec_id = str(props.get('prec_2022', props.get('precinct', '')))
            if prec_id in precinct_data:
                feat['properties'].update(precinct_data[prec_id])
                matched += 1
            else:
                feat['properties'].update({
                    'voter_count': 0, 'mean_support_score': 0, 'mean_turnout': 0,
                    'base_pct': 0, 'opposition_pct': 0, 'persuasion_pct': 0,
                    'base_dropoff_pct': 0, 'maga_pct': 0, 'saikat_pct': 0,
                    'persuasion_priority_pct': 0, 'mean_vote_freq': 0,
                })
        print(f"       Matched {matched}/{len(geo['features'])} features")
        if matched < 50:
            print("       Poor match rate, falling back to district polygons")
            geo = None
    except Exception as e:
        print(f"       Download failed: {e}")
        geo = None

# If still no geo, build simple district-level placeholder
if geo is None:
    print("       Building district-level fallback geometry ...")
    # Simple bounding boxes for SF supervisor districts (approximate)
    geo = {"type": "FeatureCollection", "features": []}
    for ds in district_summaries:
        geo['features'].append({
            "type": "Feature",
            "properties": {
                "precinct": f"District {ds['district']}",
                "supervisor_district": str(ds['district']),
                "voter_count": ds['total_voters'],
                "mean_support_score": ds['mean_score'],
                "mean_turnout": ds['mean_turnout'],
                "base_pct": ds['base_pct'],
                "opposition_pct": ds['opposition_pct'],
                "persuasion_pct": ds['persuasion_pct'],
                "base_dropoff_pct": round(ds['base_dropoff_count'] / ds['total_voters'] * 100, 1),
                "maga_pct": round(ds['maga_count'] / ds['total_voters'] * 100, 1),
                "saikat_pct": round(ds['saikat_count'] / ds['total_voters'] * 100, 1),
                "persuasion_priority_pct": 0,
                "mean_vote_freq": 0,
            },
            "geometry": {"type": "Point", "coordinates": [-122.44, 37.76]}
        })

# Build district-level GeoJSON by dissolving precincts into districts
print("       Building district boundary GeoJSON ...")
district_geo = {"type": "FeatureCollection", "features": []}
# Group precinct features by district
from collections import defaultdict
dist_features = defaultdict(list)
for feat in geo['features']:
    prec_id = str(feat['properties'].get('precinct', ''))
    dist = precinct_data.get(prec_id, {}).get('district', 0)
    if dist and dist > 0:
        dist_features[dist].append(feat)

# For each district, collect all polygon coordinates (simplified merge)
for dist_num in sorted(dist_features.keys()):
    feats = dist_features[dist_num]
    # Collect all polygons from all precincts in this district
    all_polys = []
    for f in feats:
        geom = f['geometry']
        if geom['type'] == 'Polygon':
            all_polys.append(geom['coordinates'])
        elif geom['type'] == 'MultiPolygon':
            all_polys.extend(geom['coordinates'])
    dd = district_map_data.get(str(dist_num), {})
    district_geo['features'].append({
        "type": "Feature",
        "properties": {
            "district": dist_num,
            **dd,
        },
        "geometry": {"type": "MultiPolygon", "coordinates": all_polys}
    })

# Build citywide GeoJSON (all precincts as one feature)
citywide_geo = {"type": "FeatureCollection", "features": []}
all_city_polys = []
for feat in geo['features']:
    geom = feat['geometry']
    if geom['type'] == 'Polygon':
        all_city_polys.append(geom['coordinates'])
    elif geom['type'] == 'MultiPolygon':
        all_city_polys.extend(geom['coordinates'])
citywide_geo['features'].append({
    "type": "Feature",
    "properties": {"district": "all", **citywide_data},
    "geometry": {"type": "MultiPolygon", "coordinates": all_city_polys}
})

district_geo_str = json.dumps(district_geo, separators=(',', ':'))
citywide_geo_str = json.dumps(citywide_geo, separators=(',', ':'))

# Serialize GeoJSON compactly
geo_json_str = json.dumps(geo, separators=(',', ':'))

# ── 6. Build SUPPORT_DATA object ────────────────────────────────────────────
print("[6/10] Building SUPPORT_DATA ...")
support_data = {
    'totals': totals,
    'scoreHistogram': score_histogram,
    'districts': district_summaries,
    'demographics': demo_breakdowns,
    'opposition': opposition_breakdown,
    'persuasion': persuasion_segments,
}
support_json_str = json.dumps(support_data, separators=(',', ':'))

# ── 7. Insert new CSS before </style> ───────────────────────────────────────
print("[7/10] Inserting new CSS ...")
new_css = """
/* ── TAB NAVIGATION ────────────────────────────────────────────── */
.nav-tabs {
    display: flex;
    background: #191a4d;
    padding: 0 32px;
    gap: 0;
}
.nav-tabs button {
    padding: 12px 24px;
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 14px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    background: transparent;
    color: rgba(255,255,255,0.6);
    border: none;
    cursor: pointer;
    border-bottom: 3px solid transparent;
    transition: all 0.2s;
}
.nav-tabs button:hover { color: #fff; }
.nav-tabs button.active {
    color: #fff;
    border-bottom-color: #f89828;
}
.tab-content { display: none; }
.tab-content.active { display: block; }

/* ── SUPPORT SUB-TABS ──────────────────────────────────────────── */
.sub-tabs {
    display: flex;
    gap: 0;
    border-bottom: 2px solid #e5e7eb;
    margin-bottom: 24px;
}
.sub-tabs button {
    padding: 10px 20px;
    font-family: 'Barlow', sans-serif;
    font-size: 13px;
    font-weight: 600;
    background: transparent;
    color: #6b7280;
    border: none;
    cursor: pointer;
    border-bottom: 3px solid transparent;
    transition: all 0.2s;
    margin-bottom: -2px;
}
.sub-tabs button:hover { color: #191a4d; }
.sub-tabs button.active {
    color: #191a4d;
    border-bottom-color: #f89828;
}
.sub-content { display: none; }
.sub-content.active { display: block; }

/* ── SUPPORT CARDS ─────────────────────────────────────────────── */
.sup-cards {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 28px;
}
.sup-card {
    background: #fff;
    border-radius: 10px;
    padding: 18px 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    border: 1px solid #e5e7eb;
}
.sup-card .sup-label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #6b7280;
    margin-bottom: 6px;
    font-weight: 600;
}
.sup-card .sup-value {
    font-size: 28px;
    font-weight: 800;
    color: #191a4d;
}
.sup-card .sup-detail {
    font-size: 11px;
    color: #9ca3af;
    margin-top: 2px;
}
.sup-card.base-card { border-top: 3px solid #191a4d; }
.sup-card.pers-card { border-top: 3px solid #f89828; }
.sup-card.opp-card  { border-top: 3px solid #94a3b8; }
.sup-card.drop-card { border-top: 3px solid #dc2626; }

/* ── CHART WRAPPERS ────────────────────────────────────────────── */
.chart-box {
    background: #fff;
    border-radius: 10px;
    padding: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    border: 1px solid #e5e7eb;
    margin-bottom: 24px;
}
.chart-box h3 {
    font-size: 14px;
    font-weight: 700;
    color: #191a4d;
    margin-bottom: 16px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.histogram-wrap { position: relative; height: 300px; }
.district-chart-wrap { position: relative; height: 350px; }
.demo-chart-wrap { position: relative; height: 320px; }
.opp-chart-wrap { position: relative; height: 280px; display: flex; justify-content: center; }

/* ── SUPPORT TABLES ────────────────────────────────────────────── */
.sup-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}
.sup-table th {
    background: #191a4d;
    color: #fff;
    padding: 10px 14px;
    text-align: left;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.sup-table th.num { text-align: right; }
.sup-table td {
    padding: 8px 14px;
    border-bottom: 1px solid #e5e7eb;
}
.sup-table td.num { text-align: right; font-variant-numeric: tabular-nums; }
.sup-table tr:hover td { background: #f9fafb; }

/* ── MAP CONTAINER ─────────────────────────────────────────────── */
#map-container {
    height: 700px;
    width: 100%;
    border-radius: 0 0 10px 10px;
}
.map-header {
    background: #191a4d;
    color: #fff;
    padding: 16px 24px;
    border-radius: 10px 10px 0 0;
    font-size: 16px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.map-controls {
    position: absolute;
    top: 16px;
    right: 16px;
    z-index: 1000;
    background: #fff;
    border-radius: 8px;
    padding: 14px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    max-height: 90%;
    overflow-y: auto;
    width: 220px;
}
.map-controls h4 {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #6b7280;
    margin-bottom: 8px;
    font-weight: 700;
}
.map-controls label {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: #374151;
    padding: 4px 0;
    cursor: pointer;
}
.map-controls input[type="radio"] { accent-color: #191a4d; }
.map-legend {
    position: absolute;
    bottom: 24px;
    left: 16px;
    z-index: 1000;
    background: #fff;
    border-radius: 8px;
    padding: 12px 16px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    font-size: 12px;
}
.map-legend h4 {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #6b7280;
    margin-bottom: 6px;
    font-weight: 700;
}
.legend-bar {
    width: 180px;
    height: 14px;
    border-radius: 3px;
    margin-bottom: 4px;
}
.legend-labels {
    display: flex;
    justify-content: space-between;
    font-size: 10px;
    color: #6b7280;
}

/* ── DEMO TOGGLE ───────────────────────────────────────────────── */
.demo-toggle {
    display: flex;
    gap: 0;
    margin-bottom: 16px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    overflow: hidden;
    width: fit-content;
}
.demo-toggle button {
    padding: 8px 18px;
    font-size: 12px;
    font-weight: 600;
    background: #fff;
    color: #374151;
    border: none;
    border-right: 1px solid #d1d5db;
    cursor: pointer;
    font-family: 'Barlow', sans-serif;
}
.demo-toggle button:last-child { border-right: none; }
.demo-toggle button.active { background: #191a4d; color: #fff; }

/* ── GEOGRAPHY TOGGLE ──────────────────────────────────────────── */
.geo-toggle {
    display: inline-flex;
    gap: 0;
    margin-left: 24px;
    border: 1px solid rgba(255,255,255,0.3);
    border-radius: 4px;
    overflow: hidden;
    vertical-align: middle;
}
.geo-toggle button {
    padding: 4px 14px;
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    background: transparent;
    color: rgba(255,255,255,0.6);
    border: none;
    border-right: 1px solid rgba(255,255,255,0.2);
    cursor: pointer;
    transition: all 0.15s;
}
.geo-toggle button:last-child { border-right: none; }
.geo-toggle button:hover { color: #fff; }
.geo-toggle button.active { background: rgba(248,152,40,0.3); color: #fff; }

/* ── NEIGHBORHOOD LABELS ──────────────────────────────────────── */
.hood-label {
    background: none !important;
    border: none !important;
    box-shadow: none !important;
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 11px;
    font-weight: 600;
    color: #374151;
    text-shadow: 1px 1px 2px #fff, -1px -1px 2px #fff, 1px -1px 2px #fff, -1px 1px 2px #fff;
    white-space: nowrap;
    pointer-events: none;
}

@media (max-width: 900px) {
    .sup-cards { grid-template-columns: repeat(2, 1fr); }
}
"""
html = html.replace('</style>', new_css + '\n</style>')

# ── 8. Restructure HTML ─────────────────────────────────────────────────────
print("[8/10] Restructuring HTML (tabs + new content) ...")

# A. Add tab navigation after header closing div
# The header is: <div class="header"> ... </div>  (line 307-310 approx)
# Find the pattern: </div>\n\n<!-- ── CONTROL BAR
# We need to insert nav-tabs between the header </div> and the controls

header_close = '</div>\n\n<!-- ── CONTROLS'
nav_tabs_html = '''</div>

<!-- ── TAB NAVIGATION ────────────────────────────────────────────── -->
<div class="nav-tabs">
    <button class="active" onclick="switchTab('turnout', this)">Turnout Model</button>
    <button onclick="switchTab('support', this)">Universes</button>
    <button onclick="switchTab('map', this)">Interactive Map</button>
</div>

<!-- ── CONTROLS'''

html = html.replace(header_close, nav_tabs_html, 1)

# B. Wrap existing controls + container in tab-turnout div
# Insert <div id="tab-turnout" class="tab-content active"> before <div class="controls">
controls_marker = '<div class="controls">'
html = html.replace(
    controls_marker,
    '<div class="tab-content active" id="tab-turnout">\n' + controls_marker,
    1
)

# Insert close of tab-turnout after </div><!-- /.container -->
container_close = '</div><!-- /.container -->'
html = html.replace(
    container_close,
    container_close + '\n</div><!-- /#tab-turnout -->',
    1
)

# C. Build Support & Universes tab HTML
support_tab_html = '''
<!-- ── SUPPORT & UNIVERSES TAB ───────────────────────────────────── -->
<div class="tab-content" id="tab-support">
<div class="container">
    <div class="sub-tabs">
        <button class="active" onclick="switchSubTab('overview', this)">Overview</button>
        <button onclick="switchSubTab('bydistrict', this)">By District</button>
        <button onclick="switchSubTab('demographics', this)">Demographics</button>
        <button onclick="switchSubTab('opposition', this)">Opposition</button>
        <button onclick="switchSubTab('persuasion', this)">Persuasion</button>
    </div>

    <!-- Overview Sub-tab -->
    <div class="sub-content active" id="sub-overview">
        <div style="margin-bottom:20px;padding:16px 20px;background:#f8f9fa;border-radius:8px;font-size:13px;line-height:1.7;color:#374151;">
            <strong style="color:#191a4d;">Base</strong> voters are reliable Scott Wiener supporters \u2014 liberal-to-moderate Democrats, often LGBTQ+ allied, concentrated in Districts 2, 3, 6, 7, and 8.
            <br><br>
            <strong style="color:#f89828;">Persuasion</strong> voters are reachable but not yet committed \u2014 moderate Democrats and NPP voters who could go either way based on campaign contact.
            <br><br>
            <strong style="color:#94a3b8;">Opposition</strong> includes MAGA-aligned voters, likely Saikat Chakrabarti supporters, and strong conservatives who are unlikely to support Scott.
            <br><br>
            <strong style="color:#dc2626;">Base Drop-off</strong> are base supporters with low turnout probability \u2014 the highest-ROI mobilization targets.
        </div>
        <div class="sup-cards" id="sup-overview-cards"></div>
        <div class="chart-box">
            <h3>Support Score Distribution</h3>
            <div class="histogram-wrap"><canvas id="histogramChart"></canvas></div>
        </div>
    </div>

    <!-- By District Sub-tab -->
    <div class="sub-content" id="sub-bydistrict">
        <div class="chart-box">
            <h3>Universe Composition by Supervisor District</h3>
            <div class="district-chart-wrap"><canvas id="districtChart"></canvas></div>
        </div>
        <div class="chart-box">
            <h3>District Detail</h3>
            <table class="sup-table" id="districtTable">
                <thead><tr>
                    <th>District</th><th class="num">Total</th><th class="num">Base</th>
                    <th class="num">Base %</th><th class="num">Persuasion %</th>
                    <th class="num">Opposition %</th><th class="num">Avg Score</th>
                </tr></thead>
                <tbody id="districtTbody"></tbody>
            </table>
        </div>
    </div>

    <!-- Demographics Sub-tab -->
    <div class="sub-content" id="sub-demographics">
        <div class="demo-toggle">
            <button class="active" onclick="switchDemo('race', this)">Race</button>
            <button onclick="switchDemo('age', this)">Age</button>
        </div>
        <div class="chart-box">
            <h3 id="demoChartTitle">Universe by Race</h3>
            <div class="demo-chart-wrap"><canvas id="demoChart"></canvas></div>
        </div>
        <div class="chart-box">
            <table class="sup-table" id="demoTable">
                <thead><tr>
                    <th>Group</th><th class="num">Total</th><th class="num">Base</th>
                    <th class="num">Persuasion</th><th class="num">Opposition</th>
                    <th class="num">Base %</th>
                </tr></thead>
                <tbody id="demoTbody"></tbody>
            </table>
        </div>
    </div>

    <!-- Opposition Sub-tab -->
    <div class="sub-content" id="sub-opposition">
        <div class="chart-box">
            <h3>Opposition Universe Breakdown</h3>
            <div style="display:flex;gap:32px;align-items:flex-start;flex-wrap:wrap;">
                <div class="opp-chart-wrap" style="width:300px;height:300px;"><canvas id="oppChart"></canvas></div>
                <div style="flex:1;min-width:300px;">
                    <table class="sup-table" id="oppTable">
                        <thead><tr>
                            <th>Type</th><th class="num">Count</th><th class="num">% of Opposition</th>
                        </tr></thead>
                        <tbody id="oppTbody"></tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <!-- Persuasion Sub-tab -->
    <div class="sub-content" id="sub-persuasion">
        <div class="chart-box">
            <h3>Persuasion Priority Segments</h3>
            <p style="color:#6b7280;font-size:13px;margin-bottom:16px;">
                Voters in the Persuasion universe flagged as priority targets, broken down by key demographics.
            </p>
            <table class="sup-table" id="persTable">
                <thead><tr>
                    <th>Segment</th><th class="num">Count</th><th class="num">Avg Score</th>
                </tr></thead>
                <tbody id="persTbody"></tbody>
            </table>
        </div>
    </div>
</div>
</div><!-- /#tab-support -->
'''

# D. Build Map tab HTML
map_tab_html = '''
<!-- ── MAP TAB ───────────────────────────────────────────────────── -->
<div class="tab-content" id="tab-map">
<div style="max-width:1400px;margin:0 auto;padding:24px 32px;">
    <div style="position:relative;">
        <div class="map-header">
            <span>Precinct-Level Voter Map</span>
            <div class="geo-toggle">
                <button class="active" onclick="switchGeo('precinct',this)">Precinct</button>
                <button onclick="switchGeo('district',this)">Sup District</button>
                <button onclick="switchGeo('citywide',this)">Citywide</button>
            </div>
        </div>
        <div id="map-container"></div>
        <div class="map-controls">
            <h4>Data Layer</h4>
            <label><input type="radio" name="mapLayer" value="mean_support_score" checked onchange="changeMapLayer(this.value)"> Support Score</label>
            <label><input type="radio" name="mapLayer" value="base_pct" onchange="changeMapLayer(this.value)"> Base %</label>
            <label><input type="radio" name="mapLayer" value="opposition_pct" onchange="changeMapLayer(this.value)"> Opposition %</label>
            <label><input type="radio" name="mapLayer" value="persuasion_pct" onchange="changeMapLayer(this.value)"> Persuasion %</label>
            <label><input type="radio" name="mapLayer" value="persuasion_priority_pct" onchange="changeMapLayer(this.value)"> Persuasion Priority %</label>
            <label><input type="radio" name="mapLayer" value="mean_turnout" onchange="changeMapLayer(this.value)"> Turnout Probability</label>
            <label><input type="radio" name="mapLayer" value="mean_vote_freq" onchange="changeMapLayer(this.value)"> Vote Frequency</label>
            <label><input type="radio" name="mapLayer" value="maga_pct" onchange="changeMapLayer(this.value)"> MAGA Density</label>
            <label><input type="radio" name="mapLayer" value="voter_count" onchange="changeMapLayer(this.value)"> Registered Voters</label>
        </div>
        <div class="map-legend" id="mapLegend">
            <h4 id="legendTitle">Support Score</h4>
            <div class="legend-bar" id="legendBar"></div>
            <div class="legend-labels"><span id="legendMin">0</span><span id="legendMax">100</span></div>
            <div id="legendDesc" style="font-size:10px;color:#6b7280;margin-top:6px;line-height:1.4;max-width:180px;"></div>
        </div>
    </div>
</div>
</div><!-- /#tab-map -->
'''

# Insert both new tabs before the EMBEDDED DATA comment
embedded_marker = '<!-- ── EMBEDDED DATA'
html = html.replace(
    embedded_marker,
    support_tab_html + '\n' + map_tab_html + '\n' + embedded_marker,
    1
)

# ── 9. Insert data constants before existing <script> with GEO_DATA ──────────
print("[9/10] Inserting data constants and JavaScript ...")

dist_map_json = json.dumps(district_map_data, separators=(',', ':'))
city_json = json.dumps(citywide_data, separators=(',', ':'))

data_script = (
    '\n<!-- ── SUPPORT & MAP DATA ──────────────────────────────────────── -->\n'
    '<script>\n'
    'const SUPPORT_DATA = ' + support_json_str + ';\n'
    'const MAP_GEO = ' + geo_json_str + ';\n'
    'const DISTRICT_MAP_DATA = ' + dist_map_json + ';\n'
    'const CITYWIDE_DATA = ' + city_json + ';\n'
    'const DISTRICT_GEO = ' + district_geo_str + ';\n'
    'const CITYWIDE_GEO = ' + citywide_geo_str + ';\n'
    '</script>\n'
)

# Insert before the embedded data script
html = html.replace(
    embedded_marker,
    data_script + '\n' + embedded_marker,
    1
)

# ── 10. Insert JavaScript logic ──────────────────────────────────────────────
# We add a new script block before </body>
new_js = r'''
<!-- ── SUPPORT & MAP LOGIC ───────────────────────────────────────── -->
<script>
// ── Tab Switching ──────────────────────────────────────────────────
function switchTab(tabId, btn) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-tabs button').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + tabId).classList.add('active');
    btn.classList.add('active');
    if (tabId === 'map') {
        setTimeout(() => { if (window.leafletMap) window.leafletMap.invalidateSize(); }, 150);
    }
    if (tabId === 'support' && !window._supportRendered) {
        renderSupport();
        window._supportRendered = true;
    }
}

function switchSubTab(subId, btn) {
    document.querySelectorAll('.sub-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.sub-tabs button').forEach(el => el.classList.remove('active'));
    document.getElementById('sub-' + subId).classList.add('active');
    btn.classList.add('active');
}

// ── Support Rendering ──────────────────────────────────────────────
let _demoChart = null, _distChart = null, _histChart = null, _oppChart = null;
let _currentDemo = 'race';

function renderSupport() {
    const d = SUPPORT_DATA;
    const t = d.totals;

    // Overview cards
    const cardsHtml = `
        <div class="sup-card base-card">
            <div class="sup-label">Base Universe</div>
            <div class="sup-value">${t.base_count.toLocaleString()}</div>
            <div class="sup-detail">${(t.base_count/t.total_voters*100).toFixed(1)}% of electorate</div>
        </div>
        <div class="sup-card pers-card">
            <div class="sup-label">Persuasion Universe</div>
            <div class="sup-value">${t.persuasion_count.toLocaleString()}</div>
            <div class="sup-detail">${(t.persuasion_count/t.total_voters*100).toFixed(1)}% of electorate</div>
        </div>
        <div class="sup-card opp-card">
            <div class="sup-label">Opposition Universe</div>
            <div class="sup-value">${t.opposition_count.toLocaleString()}</div>
            <div class="sup-detail">${(t.opposition_count/t.total_voters*100).toFixed(1)}% of electorate</div>
        </div>
        <div class="sup-card drop-card">
            <div class="sup-label">Base Drop-off</div>
            <div class="sup-value">${t.base_dropoff_count.toLocaleString()}</div>
            <div class="sup-detail">${(t.base_dropoff_count/t.total_voters*100).toFixed(1)}% of electorate</div>
        </div>
    `;
    document.getElementById('sup-overview-cards').innerHTML = cardsHtml;

    // Histogram
    renderHistogram(d.scoreHistogram);

    // District chart + table
    renderDistrictChart(d.districts);
    renderDistrictTable(d.districts);

    // Demographics
    renderDemoContent('race');

    // Opposition
    renderOpposition(d.opposition);

    // Persuasion
    renderPersuasion(d.persuasion);
}

function renderHistogram(hist) {
    const ctx = document.getElementById('histogramChart').getContext('2d');
    const labels = hist.map(h => h.label);
    const counts = hist.map(h => h.count);
    const colors = hist.map(h => {
        const low = parseInt(h.label.split('-')[0]);
        if (low >= 65) return '#191a4d';
        if (low >= 40) return '#f89828';
        return '#94a3b8';
    });
    if (_histChart) _histChart.destroy();
    _histChart = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets: [{ data: counts, backgroundColor: colors, borderWidth: 0 }] },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: ctx => ctx.parsed.y.toLocaleString() + ' voters' } }
            },
            scales: {
                x: { grid: { display: false }, ticks: { font: { size: 10 } } },
                y: { grid: { color: '#e5e7eb' }, ticks: { callback: v => (v/1000).toFixed(0) + 'k', font: { size: 10 } } }
            }
        }
    });
}

function renderDistrictChart(districts) {
    const ctx = document.getElementById('districtChart').getContext('2d');
    const labels = districts.map(d => 'D' + d.district);
    if (_distChart) _distChart.destroy();
    _distChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                { label: 'Base', data: districts.map(d => d.base_count), backgroundColor: '#191a4d' },
                { label: 'Persuasion', data: districts.map(d => d.persuasion_count), backgroundColor: '#f89828' },
                { label: 'Opposition', data: districts.map(d => d.opposition_count), backgroundColor: '#94a3b8' },
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { position: 'top', labels: { font: { size: 11 } } } },
            scales: {
                x: { stacked: true, grid: { display: false } },
                y: { stacked: true, grid: { color: '#e5e7eb' }, ticks: { callback: v => (v/1000).toFixed(0) + 'k' } }
            }
        }
    });
}

function renderDistrictTable(districts) {
    const tbody = document.getElementById('districtTbody');
    tbody.innerHTML = districts.map(d => `<tr>
        <td>District ${d.district}</td>
        <td class="num">${d.total_voters.toLocaleString()}</td>
        <td class="num">${d.base_count.toLocaleString()}</td>
        <td class="num">${d.base_pct}%</td>
        <td class="num">${d.persuasion_pct}%</td>
        <td class="num">${d.opposition_pct}%</td>
        <td class="num">${d.mean_score}</td>
    </tr>`).join('');
}

function switchDemo(demoType, btn) {
    _currentDemo = demoType;
    document.querySelectorAll('.demo-toggle button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    renderDemoContent(demoType);
}

function renderDemoContent(demoType) {
    const data = SUPPORT_DATA.demographics[demoType];
    const titleMap = { party: 'Universe by Party', race: 'Universe by Race', age: 'Universe by Age Group' };
    document.getElementById('demoChartTitle').textContent = titleMap[demoType] || 'Universe Breakdown';

    // Chart
    const ctx = document.getElementById('demoChart').getContext('2d');
    if (_demoChart) _demoChart.destroy();
    _demoChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.map(d => d.group),
            datasets: [
                { label: 'Base', data: data.map(d => d.base_count), backgroundColor: '#191a4d' },
                { label: 'Persuasion', data: data.map(d => d.persuasion_count), backgroundColor: '#f89828' },
                { label: 'Opposition', data: data.map(d => d.opposition_count), backgroundColor: '#94a3b8' },
            ]
        },
        options: {
            indexAxis: 'y',
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { position: 'top', labels: { font: { size: 11 } } } },
            scales: {
                x: { stacked: true, grid: { color: '#e5e7eb' }, ticks: { callback: v => (v/1000).toFixed(0) + 'k' } },
                y: { stacked: true, grid: { display: false }, ticks: { font: { size: 11 } } }
            }
        }
    });

    // Table
    const tbody = document.getElementById('demoTbody');
    tbody.innerHTML = data.map(d => `<tr>
        <td>${d.group}</td>
        <td class="num">${d.total.toLocaleString()}</td>
        <td class="num">${d.base_count.toLocaleString()}</td>
        <td class="num">${d.persuasion_count.toLocaleString()}</td>
        <td class="num">${d.opposition_count.toLocaleString()}</td>
        <td class="num">${d.base_pct}%</td>
    </tr>`).join('');
}

function renderOpposition(opp) {
    const ctx = document.getElementById('oppChart').getContext('2d');
    const oppColors = { 'MAGA': '#dc2626', 'Saikat-likely': '#d97706', 'Conservative': '#475569', 'Low-score': '#94a3b8' };
    if (_oppChart) _oppChart.destroy();
    _oppChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: opp.map(o => o.type),
            datasets: [{ data: opp.map(o => o.count), backgroundColor: opp.map(o => oppColors[o.type] || '#cbd5e1') }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom', labels: { font: { size: 11 }, padding: 12 } },
                tooltip: { callbacks: { label: ctx => ctx.label + ': ' + ctx.parsed.toLocaleString() + ' (' + opp[ctx.dataIndex].pct + '%)' } }
            }
        }
    });
    const tbody = document.getElementById('oppTbody');
    tbody.innerHTML = opp.map(o => `<tr>
        <td>${o.type}</td>
        <td class="num">${o.count.toLocaleString()}</td>
        <td class="num">${o.pct}%</td>
    </tr>`).join('');
}

function renderPersuasion(segs) {
    const tbody = document.getElementById('persTbody');
    tbody.innerHTML = segs.map(s => `<tr>
        <td>${s.segment}</td>
        <td class="num">${s.count.toLocaleString()}</td>
        <td class="num">${s.mean_score}</td>
    </tr>`).join('');
}

// ── Map ────────────────────────────────────────────────────────────
const LAYER_CONFIG = {
    mean_support_score: {
        title: 'Support Score',
        desc: 'Composite 0\u2013100 score predicting likelihood of supporting Scott Wiener',
        colorType: 'diverging', min: 0, max: 100, fmt: v => v.toFixed(1)
    },
    base_pct: {
        title: 'Base %',
        desc: 'Percentage of voters assigned to Scott Wiener\u2019s base universe (score \u2265 65)',
        color: '#f89828', colorType: 'single_orange', min: 0, max: 100, fmt: v => v.toFixed(1) + '%'
    },
    opposition_pct: {
        title: 'Opposition %',
        desc: 'Percentage of voters identified as opposition (MAGA + Saikat supporters + conservative)',
        color: '#16a34a', colorType: 'single_green', min: 0, max: 100, fmt: v => v.toFixed(1) + '%'
    },
    persuasion_pct: {
        title: 'Persuasion %',
        desc: 'Percentage of voters in the persuasion universe (score 40\u201364)',
        color: '#f89828', colorType: 'single', min: 0, max: 100, fmt: v => v.toFixed(1) + '%'
    },
    persuasion_priority_pct: {
        title: 'Persuasion Priority %',
        desc: 'Percentage flagged as high-priority persuasion targets (API, Jewish, young male, renter)',
        color: '#d97706', colorType: 'single', min: 0, max: 70, fmt: v => v.toFixed(1) + '%'
    },
    mean_turnout: {
        title: 'Turnout Probability',
        desc: 'TargetSmart-modeled turnout probability for non-presidential primaries (0\u2013100)',
        colorType: 'turnout', min: 0, max: 100, fmt: v => v.toFixed(1)
    },
    mean_vote_freq: {
        title: 'Vote Frequency',
        desc: 'Historical participation rate across 6 recent elections, scaled 0\u2013100',
        color: '#7c3aed', colorType: 'single', min: 0, max: 100, fmt: v => v.toFixed(1)
    },
    maga_pct: {
        title: 'MAGA Density',
        desc: 'Percentage of voters with Trump support score > 50',
        color: '#dc2626', colorType: 'single', min: 0, max: 30, fmt: v => v.toFixed(1) + '%'
    },
    voter_count: {
        title: 'Registered Voters',
        desc: 'Total registered voters in this area',
        color: '#4f46e5', colorType: 'single', min: 0, max: 2000, fmt: v => Math.round(v).toLocaleString()
    },
};

let _currentLayer = 'mean_support_score';
let _geoLayer = null;
let _distOverlay = null;
let _geoLevel = 'precinct';
let _hoodLabels = [];

// SF Neighborhood label positions
const SF_NEIGHBORHOODS = [
    {name:"Marina",lat:37.8015,lng:-122.4368},
    {name:"Pac Heights",lat:37.7925,lng:-122.4355},
    {name:"North Beach",lat:37.8060,lng:-122.4103},
    {name:"FiDi",lat:37.7946,lng:-122.3999},
    {name:"SoMa",lat:37.7785,lng:-122.3950},
    {name:"Tenderloin",lat:37.7847,lng:-122.4137},
    {name:"Hayes Valley",lat:37.7760,lng:-122.4260},
    {name:"Castro",lat:37.7609,lng:-122.4350},
    {name:"Mission",lat:37.7599,lng:-122.4148},
    {name:"Noe Valley",lat:37.7502,lng:-122.4337},
    {name:"Haight",lat:37.7692,lng:-122.4481},
    {name:"Inner Sunset",lat:37.7602,lng:-122.4630},
    {name:"Outer Sunset",lat:37.7553,lng:-122.4955},
    {name:"Richmond",lat:37.7800,lng:-122.4800},
    {name:"Potrero Hill",lat:37.7605,lng:-122.3925},
    {name:"Bernal Heights",lat:37.7388,lng:-122.4159},
    {name:"Glen Park",lat:37.7340,lng:-122.4332},
    {name:"Excelsior",lat:37.7234,lng:-122.4240},
    {name:"Bayview",lat:37.7307,lng:-122.3886},
    {name:"Presidio",lat:37.7989,lng:-122.4662},
    {name:"W. Addition",lat:37.7815,lng:-122.4340},
    {name:"Twin Peaks",lat:37.7544,lng:-122.4477},
    {name:"Dogpatch",lat:37.7615,lng:-122.3870},
    {name:"Japantown",lat:37.7852,lng:-122.4295},
    {name:"West Portal",lat:37.7400,lng:-122.4630},
    {name:"Ingleside",lat:37.7236,lng:-122.4490},
    {name:"Nob Hill",lat:37.7930,lng:-122.4161},
    {name:"Mission Bay",lat:37.7710,lng:-122.3910},
];

function initMap() {
    if (window.leafletMap) return;
    const map = L.map('map-container', { scrollWheelZoom: true }).setView([37.76, -122.44], 12);
    // No-labels base map for cleaner look
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', {
        attribution: '\u00a9 OSM \u00a9 CARTO',
        maxZoom: 19
    }).addTo(map);
    window.leafletMap = map;
    addNeighborhoodLabels(map);
    renderGeoLayer(_currentLayer);
}

function addNeighborhoodLabels(map) {
    SF_NEIGHBORHOODS.forEach(h => {
        const marker = L.marker([h.lat, h.lng], {
            icon: L.divIcon({ className: 'hood-label', html: h.name, iconSize: null })
        });
        marker.addTo(map);
        _hoodLabels.push(marker);
    });
}

function toggleNeighborhoods(show) {
    const map = window.leafletMap;
    if (!map) return;
    _hoodLabels.forEach(m => { show ? m.addTo(map) : map.removeLayer(m); });
}

function getFeatureValue(feature, layerKey) {
    return feature.properties[layerKey] || 0;
}

function getColor(value, layerKey) {
    const cfg = LAYER_CONFIG[layerKey];
    // Quantize to 5-point steps for sharper visual contrast
    const step = 5;
    const qv = Math.floor(value / step) * step;
    if (cfg.colorType === 'diverging') {
        // Green (low/opposition) -> white (50) -> orange (high/Scott support)
        const mid = (cfg.max + cfg.min) / 2;
        if (qv >= mid) {
            const t = Math.min(1, (qv - mid) / (cfg.max - mid));
            // Apply power curve for faster ramp
            const tp = Math.pow(t, 0.6);
            return `rgb(${255},${Math.round(255-(255-152)*tp)},${Math.round(255-(255-40)*tp)})`;
        } else {
            const t = Math.min(1, (mid - qv) / (mid - cfg.min));
            const tp = Math.pow(t, 0.6);
            return `rgb(${Math.round(255-(255-34)*tp)},${Math.round(255-(255-139)*tp)},${Math.round(255-(255-34)*tp)})`;
        }
    } else if (cfg.colorType === 'single_orange') {
        const t = Math.max(0, Math.min(1, (qv - cfg.min) / (cfg.max - cfg.min)));
        const tp = Math.pow(t, 0.6);
        return `rgb(255,${Math.round(255-(255-152)*tp)},${Math.round(255-(255-40)*tp)})`;
    } else if (cfg.colorType === 'single_green') {
        const t = Math.max(0, Math.min(1, (qv - cfg.min) / (cfg.max - cfg.min)));
        const tp = Math.pow(t, 0.6);
        return `rgb(${Math.round(255-(255-22)*tp)},${Math.round(255-(255-163)*tp)},${Math.round(255-(255-74)*tp)})`;
    } else if (cfg.colorType === 'turnout') {
        if (qv < 10) return '#f0f0f0';
        const t = Math.min(1, (qv - 10) / (cfg.max - 10));
        const tp = Math.pow(t, 0.6);
        return `rgb(${Math.round(220-206*tp)},${Math.round(230-153*tp)},${Math.round(245-99*tp)})`;
    } else {
        const t = Math.max(0, Math.min(1, (qv - cfg.min) / (cfg.max - cfg.min)));
        const tp = Math.pow(t, 0.6);
        const hex = cfg.color;
        const r = parseInt(hex.slice(1,3),16), g = parseInt(hex.slice(3,5),16), b = parseInt(hex.slice(5,7),16);
        return `rgb(${Math.round(255+(r-255)*tp)},${Math.round(255+(g-255)*tp)},${Math.round(255+(b-255)*tp)})`;
    }
}

function getGeoSource() {
    if (_geoLevel === 'district') return DISTRICT_GEO;
    if (_geoLevel === 'citywide') return CITYWIDE_GEO;
    return MAP_GEO;
}

function renderGeoLayer(layerKey) {
    const map = window.leafletMap;
    if (_geoLayer) map.removeLayer(_geoLayer);
    if (_distOverlay) { map.removeLayer(_distOverlay); _distOverlay = null; }
    const geoSource = getGeoSource();
    const isPrecinct = _geoLevel === 'precinct';
    // For district/citywide: no stroke on fill layer (precinct lines hidden)
    const fillWeight = isPrecinct ? 1 : 0;
    const fillColor = isPrecinct ? 'rgba(55,65,81,0.7)' : 'transparent';
    const fillOpac = isPrecinct ? 0.8 : 0;
    _geoLayer = L.geoJSON(geoSource, {
        style: function(feature) {
            const val = getFeatureValue(feature, layerKey);
            return {
                fillColor: getColor(val, layerKey),
                weight: fillWeight,
                opacity: fillOpac,
                color: fillColor,
                fillOpacity: 0.8
            };
        },
        onEachFeature: function(feature, layer) {
            layer.on('click', function(e) {
                const p = feature.properties;
                const label = isPrecinct ?
                    `Precinct ${p.precinct || '?'}` :
                    (_geoLevel === 'district' ? `Sup District ${p.district || '?'}` : 'Citywide');
                const popup = `
                    <div style="font-size:12px;line-height:1.6;">
                        <strong style="font-size:13px;">${label}</strong>
                        <hr style="margin:6px 0;border:none;border-top:1px solid #e5e7eb;">
                        <b>Voters:</b> ${(p.voter_count||0).toLocaleString()}<br>
                        <b>Support Score:</b> ${(p.mean_support_score||0).toFixed(1)}<br>
                        <b>Turnout:</b> ${(p.mean_turnout||0).toFixed(1)}<br>
                        <b>Vote Freq:</b> ${(p.mean_vote_freq||0).toFixed(1)}<br>
                        <hr style="margin:6px 0;border:none;border-top:1px solid #e5e7eb;">
                        <b>Base:</b> ${(p.base_pct||0).toFixed(1)}%<br>
                        <b>Persuasion:</b> ${(p.persuasion_pct||0).toFixed(1)}%<br>
                        <b>Opposition:</b> ${(p.opposition_pct||0).toFixed(1)}%<br>
                        <b>MAGA:</b> ${(p.maga_pct||0).toFixed(1)}%
                    </div>`;
                L.popup().setLatLng(e.latlng).setContent(popup).openOn(map);
            });
            layer.on('mouseover', function() {
                if (isPrecinct) {
                    this.setStyle({ weight: 2.5, color: '#191a4d' });
                    this.bringToFront();
                }
            });
            layer.on('mouseout', function() {
                if (isPrecinct) _geoLayer.resetStyle(this);
            });
        }
    }).addTo(map);
    // Overlay boundary lines on top (no fill, just outlines)
    if (typeof DISTRICT_GEO !== 'undefined') {
        const bWeight = isPrecinct ? 2.5 : (_geoLevel === 'district' ? 2.5 : 0);
        const bDash = isPrecinct ? '6,4' : '';
        const bOpacity = isPrecinct ? 0.6 : 0.9;
        if (bWeight > 0) {
            _distOverlay = L.geoJSON(DISTRICT_GEO, {
                style: { fillColor: 'transparent', fillOpacity: 0, weight: bWeight, color: '#191a4d', opacity: bOpacity, dashArray: bDash },
                interactive: false
            }).addTo(map);
        }
    }
    // For citywide, add a single city boundary outline
    if (_geoLevel === 'citywide' && typeof CITYWIDE_GEO !== 'undefined') {
        _distOverlay = L.geoJSON(CITYWIDE_GEO, {
            style: { fillColor: 'transparent', fillOpacity: 0, weight: 3, color: '#191a4d', opacity: 0.9 },
            interactive: false
        }).addTo(map);
    }
    updateLegend(layerKey);
}

function changeMapLayer(layerKey) {
    _currentLayer = layerKey;
    if (!window.leafletMap) { initMap(); return; }
    renderGeoLayer(layerKey);
}

function switchGeo(level, btn) {
    _geoLevel = level;
    document.querySelectorAll('.geo-toggle button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    if (window.leafletMap) renderGeoLayer(_currentLayer);
}

function updateLegend(layerKey) {
    const cfg = LAYER_CONFIG[layerKey];
    document.getElementById('legendTitle').textContent = cfg.title;
    document.getElementById('legendDesc').textContent = cfg.desc;
    document.getElementById('legendMin').textContent = cfg.min;
    document.getElementById('legendMax').textContent = cfg.max;
    const bar = document.getElementById('legendBar');
    if (cfg.colorType === 'diverging') {
        bar.style.background = 'linear-gradient(to right, #228b22, #ffffff 50%, #f89828)';
    } else if (cfg.colorType === 'single_orange') {
        bar.style.background = 'linear-gradient(to right, #ffffff, #f89828)';
    } else if (cfg.colorType === 'single_green') {
        bar.style.background = 'linear-gradient(to right, #ffffff, #16a34a)';
    } else if (cfg.colorType === 'turnout') {
        bar.style.background = 'linear-gradient(to right, #f0f0f0 10%, #0e4d92)';
    } else {
        bar.style.background = 'linear-gradient(to right, #ffffff, ' + cfg.color + ')';
    }
}

// ── Initialize map on first tab switch ─────────────────────────────
const _mapObserver = new MutationObserver(() => {
    const mapTab = document.getElementById('tab-map');
    if (mapTab && mapTab.classList.contains('active') && !window.leafletMap) {
        setTimeout(initMap, 200);
    }
});
_mapObserver.observe(document.body, { subtree: true, attributes: true, attributeFilter: ['class'] });
</script>
'''

# Insert before </body>
html = html.replace('</body>', new_js + '\n</body>')

# ── Write output ─────────────────────────────────────────────────────────────
print("[10/10] Writing output ...")
os.makedirs(os.path.dirname(OUT_HTML), exist_ok=True)
with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)

size_mb = os.path.getsize(OUT_HTML) / (1024 * 1024)
lines = html.count('\n') + 1
print(f"\nDone! Output: {OUT_HTML}")
print(f"  Size: {size_mb:.2f} MB")
print(f"  Lines: {lines:,}")
print(f"  Voter data: {len(df):,} voters across {len(precinct_data)} precincts")
print(f"  GeoJSON features: {len(geo['features'])}")
print(f"  Districts: {len(district_summaries)}")
