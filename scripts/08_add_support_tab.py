#!/usr/bin/env python3
"""
08_add_support_tab.py
Reads the existing turnout dashboard HTML and inserts a new
"Support & Universes" tabbed section. Aggregates voter-level data
from cd11_voters_with_scores.csv into compact JSON summaries.
Writes the modified dashboard to turnout_dashboard_v2.html.
"""

import csv
import json
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent.parent
DASHBOARD_IN = BASE / "dashboard" / "turnout_dashboard.html"
DASHBOARD_OUT = BASE / "dashboard" / "turnout_dashboard_v2.html"
VOTERS_CSV = BASE / "data" / "processed" / "cd11_voters_with_scores.csv"
UNIVERSE_CSV = BASE / "data" / "processed" / "universe_summary.csv"

# ── Colors ─────────────────────────────────────────────────────────
NAVY = "#1B2A4A"
GOLD = "#E8A630"
GRAY = "#94a3b8"


def load_and_aggregate():
    """Read the large voter CSV and compute all aggregations we need."""
    print(f"  Reading {VOTERS_CSV.name} ...")

    total = 0
    universe_counts = Counter()
    base_dropoff_count = 0
    persuasion_priority_count = 0

    # Score histogram bins (0-4, 5-9, ..., 95-100)
    score_bins = [0] * 20

    # By supervisor district
    dist_universe = defaultdict(Counter)   # dist -> {Base: n, ...}

    # By party
    party_universe = defaultdict(Counter)
    # By race
    race_universe = defaultdict(Counter)
    # By age group
    age_universe = defaultdict(Counter)

    # Opposition breakdown
    opp_type_counts = Counter()

    # Persuasion priority flags - cross-tabulated with specific columns
    # We need counts for: API voters, Male 18-49, etc.
    pp_api = 0
    pp_male_18_49 = 0
    pp_total = 0

    # Persuasion priority by specific groups
    pp_by_party = Counter()
    pp_by_race = Counter()

    with open(VOTERS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            universe = row["universe"]
            universe_counts[universe] += 1

            # Score histogram
            try:
                score = float(row["support_score"])
                bin_idx = min(int(score // 5), 19)
                score_bins[bin_idx] += 1
            except (ValueError, KeyError):
                pass

            # District
            dist = row.get("CountySupervisorName", "")
            if dist:
                dist_universe[dist][universe] += 1

            # Party
            party = row.get("Party", "")
            if party:
                party_universe[party][universe] += 1

            # Race
            race = row.get("RaceName", "")
            if race:
                race_universe[race][universe] += 1

            # Age group
            try:
                age = float(row.get("Age", "0"))
                if age < 30:
                    ag = "18-29"
                elif age < 40:
                    ag = "30-39"
                elif age < 50:
                    ag = "40-49"
                elif age < 65:
                    ag = "50-64"
                else:
                    ag = "65+"
                age_universe[ag][universe] += 1
            except ValueError:
                pass

            # Base drop-off
            if row.get("base_dropoff") == "True":
                base_dropoff_count += 1

            # Opposition type
            if universe == "Opposition":
                ot = row.get("opposition_type", "")
                if ot:
                    opp_type_counts[ot] += 1

            # Persuasion priority
            if row.get("persuasion_priority") == "True":
                pp_total += 1
                if row.get("RaceName", "") == "Asian or Pacific Islander":
                    pp_api += 1
                if row.get("Sex", "") == "M":
                    try:
                        age_val = float(row.get("Age", "0"))
                        if 18 <= age_val < 50:
                            pp_male_18_49 += 1
                    except ValueError:
                        pass
                pp_by_party[row.get("Party", "")] += 1
                pp_by_race[row.get("RaceName", "")] += 1

    print(f"  Processed {total:,} voter records")
    return {
        "total": total,
        "universe_counts": dict(universe_counts),
        "base_dropoff_count": base_dropoff_count,
        "score_bins": score_bins,
        "dist_universe": {k: dict(v) for k, v in dist_universe.items()},
        "party_universe": {k: dict(v) for k, v in party_universe.items()},
        "race_universe": {k: dict(v) for k, v in race_universe.items()},
        "age_universe": {k: dict(v) for k, v in age_universe.items()},
        "opp_type_counts": dict(opp_type_counts),
        "pp_total": pp_total,
        "pp_api": pp_api,
        "pp_male_18_49": pp_male_18_49,
        "pp_by_party": dict(pp_by_party),
        "pp_by_race": dict(pp_by_race),
    }


def build_support_data_js(agg):
    """Build the JavaScript const SUPPORT_DATA = {...} string."""
    data = {
        "total": agg["total"],
        "universes": {
            "Base": agg["universe_counts"].get("Base", 0),
            "Persuasion": agg["universe_counts"].get("Persuasion", 0),
            "Opposition": agg["universe_counts"].get("Opposition", 0),
        },
        "baseDropoff": agg["base_dropoff_count"],
        "scoreBins": agg["score_bins"],
        "byDistrict": {},
        "byParty": {},
        "byRace": {},
        "byAge": {},
        "oppositionTypes": agg["opp_type_counts"],
        "persuasionPriority": {
            "total": agg["pp_total"],
            "api": agg["pp_api"],
            "male18_49": agg["pp_male_18_49"],
            "byParty": agg["pp_by_party"],
            "byRace": agg["pp_by_race"],
        },
    }

    # Districts (sorted numerically 1-10)
    for d in sorted(agg["dist_universe"].keys(), key=lambda x: int(x)):
        data["byDistrict"][d] = {
            "Base": agg["dist_universe"][d].get("Base", 0),
            "Persuasion": agg["dist_universe"][d].get("Persuasion", 0),
            "Opposition": agg["dist_universe"][d].get("Opposition", 0),
        }

    # Party mapping for display
    party_labels = {"D": "Democrat", "R": "Republican", "U": "No Party Pref",
                    "G": "Green", "L": "Libertarian", "P": "Peace & Freedom",
                    "O": "Other"}
    for p in ["D", "R", "U", "G", "L", "P", "O"]:
        if p in agg["party_universe"]:
            data["byParty"][party_labels.get(p, p)] = {
                "Base": agg["party_universe"][p].get("Base", 0),
                "Persuasion": agg["party_universe"][p].get("Persuasion", 0),
                "Opposition": agg["party_universe"][p].get("Opposition", 0),
            }

    # Race
    for r in sorted(agg["race_universe"].keys()):
        data["byRace"][r] = {
            "Base": agg["race_universe"][r].get("Base", 0),
            "Persuasion": agg["race_universe"][r].get("Persuasion", 0),
            "Opposition": agg["race_universe"][r].get("Opposition", 0),
        }

    # Age groups (ordered)
    for ag in ["18-29", "30-39", "40-49", "50-64", "65+"]:
        if ag in agg["age_universe"]:
            data["byAge"][ag] = {
                "Base": agg["age_universe"][ag].get("Base", 0),
                "Persuasion": agg["age_universe"][ag].get("Persuasion", 0),
                "Opposition": agg["age_universe"][ag].get("Opposition", 0),
            }

    return f"const SUPPORT_DATA = {json.dumps(data)};"


def build_css():
    """Return the CSS block for the Support & Universes section."""
    return """
/* ── SUPPORT & UNIVERSES TAB ──────────────────────────────────── */
.support-tabs {
    display: flex;
    border-bottom: 2px solid #e5e7eb;
    margin-bottom: 20px;
    gap: 0;
    overflow-x: auto;
}
.support-tab {
    padding: 10px 20px;
    font-size: 13px;
    font-weight: 600;
    color: #6b7280;
    cursor: pointer;
    border-bottom: 3px solid transparent;
    transition: all 0.15s;
    white-space: nowrap;
    background: none;
    border-top: none;
    border-left: none;
    border-right: none;
    font-family: inherit;
}
.support-tab:hover {
    color: #1B2A4A;
    background: #f8fafc;
}
.support-tab.active {
    color: #1B2A4A;
    border-bottom-color: #E8A630;
}
.support-panel {
    display: none;
}
.support-panel.active {
    display: block;
}
.support-cards {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 24px;
}
.support-card {
    background: #f8fafc;
    border-radius: 10px;
    padding: 18px 20px;
    border: 1px solid #e5e7eb;
}
.support-card .sc-label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #6b7280;
    margin-bottom: 6px;
    font-weight: 600;
}
.support-card .sc-value {
    font-size: 28px;
    font-weight: 700;
    color: #1B2A4A;
}
.support-card .sc-detail {
    font-size: 12px;
    color: #6b7280;
    margin-top: 4px;
}
.support-card.base-card { border-left: 4px solid #1B2A4A; }
.support-card.persuasion-card { border-left: 4px solid #E8A630; }
.support-card.opposition-card { border-left: 4px solid #94a3b8; }
.support-card.dropoff-card { border-left: 4px solid #dc2626; }

.support-chart-wrap {
    position: relative;
    width: 100%;
    max-height: 420px;
    margin-bottom: 16px;
}
.support-chart-wrap canvas {
    width: 100% !important;
}
.support-chart-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
    margin-bottom: 16px;
}
.support-chart-row .chart-col {
    min-width: 0;
}
.support-demo-toggle {
    display: flex;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    overflow: hidden;
    margin-bottom: 16px;
    width: fit-content;
}
.support-demo-toggle button {
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    background: #fff;
    color: #374151;
    border: none;
    border-right: 1px solid #d1d5db;
    transition: all 0.15s;
    font-family: inherit;
}
.support-demo-toggle button:last-child { border-right: none; }
.support-demo-toggle button.active {
    background: #1B2A4A;
    color: #fff;
}
.priority-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}
.priority-table th {
    text-align: left;
    padding: 10px 12px;
    background: #f8fafc;
    border-bottom: 2px solid #e2e8f0;
    font-weight: 600;
    color: #475569;
}
.priority-table td {
    padding: 8px 12px;
    border-bottom: 1px solid #f1f5f9;
}
.priority-table tr:hover td { background: #f8fafc; }
.priority-table td.num { text-align: right; font-variant-numeric: tabular-nums; }
.priority-table th.num { text-align: right; }
.universe-badge {
    display: inline-block;
    width: 12px;
    height: 12px;
    border-radius: 3px;
    margin-right: 6px;
    vertical-align: middle;
}
@media (max-width: 1024px) {
    .support-cards { grid-template-columns: repeat(2, 1fr); }
    .support-chart-row { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
    .support-cards { grid-template-columns: 1fr; }
}
"""


def build_html():
    """Return the HTML block for the Support & Universes section."""
    return """
<!-- ── SUPPORT & UNIVERSES ─────────────────────────────────────── -->
<div class="section" id="support_section">
    <h2>Support &amp; Universes</h2>

    <div class="support-tabs" id="support_tabs">
        <button class="support-tab active" data-panel="sup_overview">Overview</button>
        <button class="support-tab" data-panel="sup_district">By District</button>
        <button class="support-tab" data-panel="sup_demo">Demographics</button>
        <button class="support-tab" data-panel="sup_opposition">Opposition</button>
        <button class="support-tab" data-panel="sup_persuasion">Persuasion</button>
    </div>

    <!-- ── Overview Panel ──────────────────────────────────────── -->
    <div class="support-panel active" id="sup_overview">
        <div class="support-cards" id="support_cards"></div>
        <div class="support-chart-wrap">
            <canvas id="support_histogram"></canvas>
        </div>
    </div>

    <!-- ── By District Panel ───────────────────────────────────── -->
    <div class="support-panel" id="sup_district">
        <div class="support-chart-wrap">
            <canvas id="district_stacked_chart"></canvas>
        </div>
        <table class="priority-table" id="district_table">
            <thead>
                <tr>
                    <th>District</th>
                    <th class="num">Base</th>
                    <th class="num">Persuasion</th>
                    <th class="num">Opposition</th>
                    <th class="num">Total</th>
                    <th class="num">Base %</th>
                </tr>
            </thead>
            <tbody id="district_tbody"></tbody>
        </table>
    </div>

    <!-- ── Demographics Panel ──────────────────────────────────── -->
    <div class="support-panel" id="sup_demo">
        <div class="support-demo-toggle" id="demo_toggle">
            <button class="active" data-dim="party">Party</button>
            <button data-dim="race">Race</button>
            <button data-dim="age">Age</button>
        </div>
        <div class="support-chart-wrap">
            <canvas id="demo_stacked_chart"></canvas>
        </div>
        <table class="priority-table" id="demo_table">
            <thead>
                <tr>
                    <th id="demo_col_header">Group</th>
                    <th class="num">Base</th>
                    <th class="num">Persuasion</th>
                    <th class="num">Opposition</th>
                    <th class="num">Total</th>
                    <th class="num">Base %</th>
                </tr>
            </thead>
            <tbody id="demo_tbody"></tbody>
        </table>
    </div>

    <!-- ── Opposition Panel ────────────────────────────────────── -->
    <div class="support-panel" id="sup_opposition">
        <div class="support-chart-row">
            <div class="chart-col">
                <div class="support-chart-wrap">
                    <canvas id="opp_doughnut"></canvas>
                </div>
            </div>
            <div class="chart-col">
                <table class="priority-table" id="opp_table">
                    <thead>
                        <tr>
                            <th>Segment</th>
                            <th class="num">Count</th>
                            <th class="num">% of Opposition</th>
                        </tr>
                    </thead>
                    <tbody id="opp_tbody"></tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- ── Persuasion Panel ────────────────────────────────────── -->
    <div class="support-panel" id="sup_persuasion">
        <p style="font-size:13px; color:#6b7280; margin-bottom:16px;">
            Persuasion-priority voters are the subset of the Persuasion universe
            most likely to be moved by direct outreach. Total: <strong id="pp_total_label"></strong>
        </p>
        <table class="priority-table" id="persuasion_table">
            <thead>
                <tr>
                    <th>Priority Segment</th>
                    <th class="num">Count</th>
                    <th class="num">% of Persuasion Priority</th>
                </tr>
            </thead>
            <tbody id="persuasion_tbody"></tbody>
        </table>
    </div>
</div>
"""


def build_js():
    """Return the JavaScript block that renders the Support section."""
    return r"""
// ── Support & Universes Logic ─────────────────────────────────────
(function() {
    const D = SUPPORT_DATA;
    const NAVY = '#1B2A4A';
    const GOLD = '#E8A630';
    const SLATE = '#94a3b8';
    const RED = '#dc2626';

    // ── Tab switching ─────────────────────────────────────────────
    document.querySelectorAll('.support-tab').forEach(function(tab) {
        tab.addEventListener('click', function() {
            document.querySelectorAll('.support-tab').forEach(function(t) { t.classList.remove('active'); });
            document.querySelectorAll('.support-panel').forEach(function(p) { p.classList.remove('active'); });
            tab.classList.add('active');
            document.getElementById(tab.getAttribute('data-panel')).classList.add('active');
        });
    });

    // ── Helper ────────────────────────────────────────────────────
    function fmt(n) { return n.toLocaleString(); }
    function pct(n, d) { return d ? (n / d * 100).toFixed(1) + '%' : '0%'; }

    // ── Overview Cards ────────────────────────────────────────────
    var cardsHtml = '';
    var base = D.universes.Base;
    var pers = D.universes.Persuasion;
    var opp = D.universes.Opposition;
    var tot = D.total;

    cardsHtml += '<div class="support-card base-card">' +
        '<div class="sc-label">Base Universe</div>' +
        '<div class="sc-value">' + fmt(base) + '</div>' +
        '<div class="sc-detail">' + pct(base, tot) + ' of registered voters</div></div>';
    cardsHtml += '<div class="support-card persuasion-card">' +
        '<div class="sc-label">Persuasion Universe</div>' +
        '<div class="sc-value">' + fmt(pers) + '</div>' +
        '<div class="sc-detail">' + pct(pers, tot) + ' of registered voters</div></div>';
    cardsHtml += '<div class="support-card opposition-card">' +
        '<div class="sc-label">Opposition Universe</div>' +
        '<div class="sc-value">' + fmt(opp) + '</div>' +
        '<div class="sc-detail">' + pct(opp, tot) + ' of registered voters</div></div>';
    cardsHtml += '<div class="support-card dropoff-card">' +
        '<div class="sc-label">Drop-off Base</div>' +
        '<div class="sc-value">' + fmt(D.baseDropoff) + '</div>' +
        '<div class="sc-detail">' + pct(D.baseDropoff, base) + ' of Base universe</div></div>';
    document.getElementById('support_cards').innerHTML = cardsHtml;

    // ── Score Histogram ───────────────────────────────────────────
    var binLabels = [];
    var binColors = [];
    for (var i = 0; i < 20; i++) {
        var lo = i * 5;
        var hi = lo + 4;
        binLabels.push(lo + '-' + hi);
        if (lo >= 65) binColors.push(NAVY);
        else if (lo >= 40) binColors.push(GOLD);
        else binColors.push(SLATE);
    }
    new Chart(document.getElementById('support_histogram'), {
        type: 'bar',
        data: {
            labels: binLabels,
            datasets: [{
                label: 'Voters',
                data: D.scoreBins,
                backgroundColor: binColors,
                borderWidth: 0,
                borderRadius: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: { display: true, text: 'Support Score Distribution', font: { size: 14, weight: '600', family: 'Montserrat' }, color: NAVY },
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(ctx) { return fmt(ctx.parsed.y) + ' voters'; },
                        afterLabel: function(ctx) {
                            var idx = ctx.dataIndex;
                            if (idx * 5 >= 65) return 'Base (score >= 65)';
                            if (idx * 5 >= 40) return 'Persuasion (40-64)';
                            return 'Opposition (< 40)';
                        }
                    }
                }
            },
            scales: {
                x: { grid: { display: false }, ticks: { font: { size: 11 } } },
                y: { ticks: { callback: function(v) { return v >= 1000 ? (v/1000).toFixed(0) + 'k' : v; }, font: { size: 11 } }, grid: { color: '#f1f5f9' } }
            }
        }
    });

    // ── District Stacked Bar ──────────────────────────────────────
    var distLabels = Object.keys(D.byDistrict).sort(function(a, b) { return parseInt(a) - parseInt(b); });
    var distBase = distLabels.map(function(d) { return D.byDistrict[d].Base || 0; });
    var distPers = distLabels.map(function(d) { return D.byDistrict[d].Persuasion || 0; });
    var distOpp = distLabels.map(function(d) { return D.byDistrict[d].Opposition || 0; });
    var distDisplayLabels = distLabels.map(function(d) { return 'District ' + d; });

    new Chart(document.getElementById('district_stacked_chart'), {
        type: 'bar',
        data: {
            labels: distDisplayLabels,
            datasets: [
                { label: 'Base', data: distBase, backgroundColor: NAVY, borderWidth: 0, borderRadius: 2 },
                { label: 'Persuasion', data: distPers, backgroundColor: GOLD, borderWidth: 0, borderRadius: 2 },
                { label: 'Opposition', data: distOpp, backgroundColor: SLATE, borderWidth: 0, borderRadius: 2 }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: { display: true, text: 'Universe by Supervisor District', font: { size: 14, weight: '600', family: 'Montserrat' }, color: NAVY },
                legend: { position: 'top', labels: { font: { size: 12, family: 'Montserrat' }, usePointStyle: true, pointStyle: 'rectRounded' } },
                tooltip: { callbacks: { label: function(ctx) { return ctx.dataset.label + ': ' + fmt(ctx.parsed.y); } } }
            },
            scales: {
                x: { stacked: true, grid: { display: false }, ticks: { font: { size: 11 } } },
                y: { stacked: true, ticks: { callback: function(v) { return v >= 1000 ? (v/1000).toFixed(0) + 'k' : v; }, font: { size: 11 } }, grid: { color: '#f1f5f9' } }
            }
        }
    });

    // District table
    var dtb = '';
    for (var di = 0; di < distLabels.length; di++) {
        var dk = distLabels[di];
        var db = D.byDistrict[dk].Base || 0;
        var dp = D.byDistrict[dk].Persuasion || 0;
        var dop = D.byDistrict[dk].Opposition || 0;
        var dtot = db + dp + dop;
        dtb += '<tr><td>District ' + dk + '</td>' +
            '<td class="num">' + fmt(db) + '</td>' +
            '<td class="num">' + fmt(dp) + '</td>' +
            '<td class="num">' + fmt(dop) + '</td>' +
            '<td class="num">' + fmt(dtot) + '</td>' +
            '<td class="num">' + pct(db, dtot) + '</td></tr>';
    }
    document.getElementById('district_tbody').innerHTML = dtb;

    // ── Demographics Panel ────────────────────────────────────────
    var demoChart = null;
    var currentDim = 'party';

    function renderDemo(dim) {
        currentDim = dim;
        var src;
        if (dim === 'party') src = D.byParty;
        else if (dim === 'race') src = D.byRace;
        else src = D.byAge;

        var labels = Object.keys(src);
        var bVals = labels.map(function(l) { return src[l].Base || 0; });
        var pVals = labels.map(function(l) { return src[l].Persuasion || 0; });
        var oVals = labels.map(function(l) { return src[l].Opposition || 0; });

        if (demoChart) demoChart.destroy();
        demoChart = new Chart(document.getElementById('demo_stacked_chart'), {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    { label: 'Base', data: bVals, backgroundColor: NAVY, borderWidth: 0, borderRadius: 2 },
                    { label: 'Persuasion', data: pVals, backgroundColor: GOLD, borderWidth: 0, borderRadius: 2 },
                    { label: 'Opposition', data: oVals, backgroundColor: SLATE, borderWidth: 0, borderRadius: 2 }
                ]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: { display: true, text: 'Universe Composition by ' + dim.charAt(0).toUpperCase() + dim.slice(1), font: { size: 14, weight: '600', family: 'Montserrat' }, color: NAVY },
                    legend: { position: 'top', labels: { font: { size: 12, family: 'Montserrat' }, usePointStyle: true, pointStyle: 'rectRounded' } },
                    tooltip: { callbacks: { label: function(ctx) { return ctx.dataset.label + ': ' + fmt(ctx.parsed.x); } } }
                },
                scales: {
                    x: { stacked: true, ticks: { callback: function(v) { return v >= 1000 ? (v/1000).toFixed(0) + 'k' : v; }, font: { size: 11 } }, grid: { color: '#f1f5f9' } },
                    y: { stacked: true, grid: { display: false }, ticks: { font: { size: 11 } } }
                }
            }
        });

        // Table
        var colHeader = dim === 'party' ? 'Party' : dim === 'race' ? 'Race/Ethnicity' : 'Age Group';
        document.getElementById('demo_col_header').textContent = colHeader;
        var tbody = '';
        for (var i = 0; i < labels.length; i++) {
            var bv = src[labels[i]].Base || 0;
            var pv = src[labels[i]].Persuasion || 0;
            var ov = src[labels[i]].Opposition || 0;
            var tv = bv + pv + ov;
            tbody += '<tr><td>' + labels[i] + '</td>' +
                '<td class="num">' + fmt(bv) + '</td>' +
                '<td class="num">' + fmt(pv) + '</td>' +
                '<td class="num">' + fmt(ov) + '</td>' +
                '<td class="num">' + fmt(tv) + '</td>' +
                '<td class="num">' + pct(bv, tv) + '</td></tr>';
        }
        document.getElementById('demo_tbody').innerHTML = tbody;
    }

    document.querySelectorAll('#demo_toggle button').forEach(function(btn) {
        btn.addEventListener('click', function() {
            document.querySelectorAll('#demo_toggle button').forEach(function(b) { b.classList.remove('active'); });
            btn.classList.add('active');
            renderDemo(btn.getAttribute('data-dim'));
        });
    });
    renderDemo('party');

    // ── Opposition Doughnut ───────────────────────────────────────
    var oppLabels = Object.keys(D.oppositionTypes);
    var oppValues = oppLabels.map(function(l) { return D.oppositionTypes[l]; });
    var oppColors = ['#dc2626', '#f97316', '#8b5cf6', '#64748b'];
    var oppTotal = oppValues.reduce(function(a, b) { return a + b; }, 0);

    new Chart(document.getElementById('opp_doughnut'), {
        type: 'doughnut',
        data: {
            labels: oppLabels,
            datasets: [{
                data: oppValues,
                backgroundColor: oppColors,
                borderWidth: 2,
                borderColor: '#fff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: { display: true, text: 'Opposition Breakdown', font: { size: 14, weight: '600', family: 'Montserrat' }, color: NAVY },
                legend: { position: 'bottom', labels: { font: { size: 12, family: 'Montserrat' }, usePointStyle: true, pointStyle: 'circle', padding: 16 } },
                tooltip: { callbacks: { label: function(ctx) { return ctx.label + ': ' + fmt(ctx.parsed) + ' (' + pct(ctx.parsed, oppTotal) + ')'; } } }
            }
        }
    });

    // Opposition table
    var otb = '';
    for (var oi = 0; oi < oppLabels.length; oi++) {
        otb += '<tr><td><span class="universe-badge" style="background:' + oppColors[oi] + '"></span>' + oppLabels[oi] + '</td>' +
            '<td class="num">' + fmt(oppValues[oi]) + '</td>' +
            '<td class="num">' + pct(oppValues[oi], oppTotal) + '</td></tr>';
    }
    document.getElementById('opp_tbody').innerHTML = otb;

    // ── Persuasion Priority ───────────────────────────────────────
    var pp = D.persuasionPriority;
    document.getElementById('pp_total_label').textContent = fmt(pp.total) + ' voters';

    var ppSegments = [
        { label: 'API (Asian/Pacific Islander) Voters', count: pp.api },
        { label: 'Male 18\u201349', count: pp.male18_49 },
        { label: 'Democrat Registrants', count: pp.byParty['D'] || 0 },
        { label: 'No Party Preference', count: pp.byParty['U'] || 0 },
        { label: 'Republican Registrants', count: pp.byParty['R'] || 0 }
    ];

    var ptb = '';
    for (var pi = 0; pi < ppSegments.length; pi++) {
        ptb += '<tr><td>' + ppSegments[pi].label + '</td>' +
            '<td class="num">' + fmt(ppSegments[pi].count) + '</td>' +
            '<td class="num">' + pct(ppSegments[pi].count, pp.total) + '</td></tr>';
    }
    document.getElementById('persuasion_tbody').innerHTML = ptb;

})();
"""


def main():
    print("=" * 60)
    print("08 \u2014 Add Support & Universes Tab to Dashboard")
    print("=" * 60)

    # 1. Read existing dashboard
    print("\n[1/5] Reading existing dashboard ...")
    if not DASHBOARD_IN.exists():
        print(f"  ERROR: {DASHBOARD_IN} not found!")
        sys.exit(1)
    html = DASHBOARD_IN.read_text(encoding="utf-8")
    print(f"  Read {len(html):,} characters ({html.count(chr(10)):,} lines)")

    # 2. Aggregate voter data
    print("\n[2/5] Aggregating voter data ...")
    if not VOTERS_CSV.exists():
        print(f"  ERROR: {VOTERS_CSV} not found!")
        sys.exit(1)
    agg = load_and_aggregate()

    # 3. Build insertion blocks
    print("\n[3/5] Building insertion blocks ...")
    css_block = build_css()
    html_block = build_html()
    js_data_block = build_support_data_js(agg)
    js_logic_block = build_js()

    # 4. Insert into HTML
    print("\n[4/5] Inserting into dashboard HTML ...")

    # Insert CSS before </style>
    style_close = "</style>"
    idx_style = html.find(style_close)
    if idx_style == -1:
        print("  ERROR: Could not find </style> tag!")
        sys.exit(1)
    html = html[:idx_style] + css_block + "\n" + html[idx_style:]
    print("  Inserted CSS block")

    # Insert HTML section before </div><!-- /.container -->
    container_close = "</div><!-- /.container -->"
    idx_container = html.find(container_close)
    if idx_container == -1:
        print("  ERROR: Could not find container close comment!")
        sys.exit(1)
    html = html[:idx_container] + html_block + "\n" + html[idx_container:]
    print("  Inserted HTML section")

    # Insert data script before the EMBEDDED DATA comment's <script> tag
    # We need to add our data AFTER the existing data script opening
    # Find the embedded data section and add our const there
    embedded_marker = "<!-- \u2500\u2500 EMBEDDED DATA"
    idx_embedded = html.find(embedded_marker)
    if idx_embedded == -1:
        print("  WARNING: Could not find EMBEDDED DATA marker, inserting before footer")
        # Fall back: insert before the footer rainbow stripe
        footer_marker = '<!-- \u2500\u2500 FOOTER'
        idx_footer = html.find(footer_marker)
        if idx_footer == -1:
            idx_footer = html.find('<div class="rainbow-stripe" style="margin-top')
        insert_pos = idx_footer
        data_script = f"\n<script>\n{js_data_block}\n</script>\n"
        html = html[:insert_pos] + data_script + html[insert_pos:]
    else:
        # Find the <script> tag right after the EMBEDDED DATA comment
        script_after = html.find("<script>", idx_embedded)
        if script_after == -1:
            print("  ERROR: Could not find script tag after EMBEDDED DATA!")
            sys.exit(1)
        # Insert right after <script>\n
        newline_after = html.find("\n", script_after)
        insert_pos = newline_after + 1
        html = html[:insert_pos] + js_data_block + "\n" + html[insert_pos:]
    print("  Inserted data constants")

    # Insert logic script before the closing </script> that contains "// ── Initial Render"
    # We want to add our logic at the end of the DASHBOARD LOGIC script block
    initial_render_marker = "// \u2500\u2500 Initial Render"
    idx_initial = html.find(initial_render_marker)
    if idx_initial == -1:
        # Fall back: insert as separate script before </body>
        body_close = "</body>"
        idx_body = html.find(body_close)
        logic_script = f"\n<script>\n{js_logic_block}\n</script>\n"
        html = html[:idx_body] + logic_script + html[idx_body:]
    else:
        # Find the </script> that closes the dashboard logic block
        script_close_after = html.find("</script>", idx_initial)
        insert_pos = script_close_after
        html = html[:insert_pos] + "\n" + js_logic_block + "\n" + html[insert_pos:]
    print("  Inserted JavaScript logic")

    # 5. Write output
    print(f"\n[5/5] Writing {DASHBOARD_OUT.name} ...")
    DASHBOARD_OUT.write_text(html, encoding="utf-8")
    size_bytes = DASHBOARD_OUT.stat().st_size
    line_count = html.count("\n") + 1

    print(f"  Written: {DASHBOARD_OUT}")
    print(f"  Size: {size_bytes:,} bytes ({size_bytes / 1024:.1f} KB)")
    print(f"  Lines: {line_count:,}")
    print(f"\n{'=' * 60}")
    print("Done! Open turnout_dashboard_v2.html in a browser to verify.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
