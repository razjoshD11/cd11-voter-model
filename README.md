# SF CD-11 Voter Targeting Model

Precinct-level voter turnout model and support-score targeting system for San Francisco's June 2026 Democratic Primary. Built for the Scott Wiener for Congress campaign (CA-11).

## What This Does

### Turnout Model (Steps 1-6)
Estimates how many voters will turn out in each SF precinct under LOW/EXPECTED/HIGH scenarios, broken down by age, race/ethnicity, and party.

### Support Scoring & Universes (Step 7)
8-factor composite support score (0-100) calibrated against EMC Research polling crosstabs. Assigns each voter to a universe:
- **Base** (score >= 65): 170,727 voters (38.1%)
- **Persuasion** (40-64): 167,890 voters (37.4%)
- **Opposition** (< 40): 109,759 voters (24.5%)

### Combined Dashboard (Step 11)
Interactive HTML dashboard with:
- Turnout model tables and charts
- Support & universes analysis (5 sub-tabs)
- Interactive Leaflet map with 9 data layers, geography toggle (precinct/district/citywide), and 28 neighborhood labels

### Targeting Memo (Step 9)
Strategic targeting memo in .docx format.

### Heat Map (Step 10)
Standalone precinct-level support heat map.

## Quick Start

```bash
# Install dependencies
pip install pandas openpyxl python-docx

# Run the full pipeline (steps 1-6 for turnout, then 7-11 for support/dashboard)
python run_all.py

# Run only support scoring + dashboard
python scripts/07_build_support_and_universes.py
python scripts/11_build_combined_dashboard.py
```

Output dashboards are generated in `dashboard/` — open in any browser.

## Pipeline Steps

| Step | Script | What It Does |
|------|--------|-------------|
| 1 | `01_build_precinct_universe.py` | Reads VAN voter file, assigns demographics, builds precinct-level counts |
| 2 | `02_calculate_historical_rates.py` | Pulls precinct-level turnout from electionmapsf.com for 4 anchor elections |
| 3 | `03_calibrate_from_polls.py` | Adjusts model using EMC Research poll crosstabs |
| 4 | `04_build_scenarios.py` | Builds LOW/EXPECTED/HIGH scenarios for Primary and General |
| 5 | `05_aggregate.py` | Rolls up precinct estimates to Sup Districts, CD11, and Citywide |
| 6 | `06_build_dashboard.py` | Generates turnout-only HTML dashboard |
| 7 | `07_build_support_and_universes.py` | Builds 8-factor support score, assigns universes |
| 8 | `08_add_support_tab.py` | (Legacy) Adds support tab to v1 dashboard |
| 9 | `09_write_targeting_memo.py` | Generates strategic targeting memo (.docx) |
| 10 | `10_build_heatmap.py` | Builds standalone support heat map |
| 11 | `11_build_combined_dashboard.py` | Builds full combined dashboard (turnout + support + map) |

## Data Sources

- **Voter file**: VAN/TargetSmart export for CD-11 (not included — contains PII)
- **Historical turnout**: electionmapsf.com precinct-level data
- **Poll calibration**: EMC Research polls (Feb 2026 n=800)
- **GeoJSON**: SF precinct boundaries (`data/geo/sf_precincts.geojson`)

## Support Score Factors

| Factor | Max Points | Key Driver |
|--------|-----------|------------|
| Ideology | 30 | Liberal/Moderate = high, Progressive/VeryProg = low |
| LGBTQ+ Proxy | 20 | HRC donation or marriage equality score |
| Geography | 15 | By Supervisor District |
| Race | 10 | API and White = higher |
| Age | 8 | Older = higher |
| Education | 7 | College grad probability |
| Vote Frequency | 5 | Recent election participation |
| Party | 5 | Democrat = highest |

## Requirements

- Python 3.8+
- pandas, numpy, openpyxl, python-docx
- Internet connection (dashboard uses Chart.js and Leaflet CDN)
