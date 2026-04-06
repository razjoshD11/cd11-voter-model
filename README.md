# SF CD-11 Voter Turnout Model

Precinct-level voter turnout model for San Francisco's June 2026 Primary and November 2026 General elections. Built for the Scott Wiener for Congress campaign (CA-11, 2026 Cycle).

## What This Does

Estimates how many voters will turn out in each SF precinct, broken down by:
- **Age**: 18-29, 30-44, 45-64, 65+
- **Race/Ethnicity**: Asian, Black, Latino/Hispanic, White, Other/Unknown
- **Party**: Democrat, Republican, NPP (No Party Preference), Other

Three scenarios for each election:
- **LOW**: Conservative floor estimate
- **EXPECTED**: Most likely outcome
- **HIGH**: Optimistic ceiling estimate

Results are available at four geographic levels:
- Citywide (all SF)
- CD-11 (Supervisor Districts 1-10, excludes District 11)
- Individual Supervisor Districts (1-11)
- Individual Precincts (~468)

## Quick Start

```bash
# Install dependencies (one time)
pip install pandas openpyxl

# Run the full pipeline
python run_all.py

# Or re-run from a specific step (e.g., after updating poll data)
python run_all.py --from 3
```

The final output is `dashboard/turnout_dashboard.html` — open it in any web browser.

## Pipeline Steps

| Step | Script | What It Does |
|------|--------|-------------|
| 1 | `01_build_precinct_universe.py` | Reads the VAN voter file, assigns demographics, builds precinct-level counts |
| 2 | `02_calculate_historical_rates.py` | Pulls precinct-level turnout from electionmapsf.com for 4 anchor elections |
| 3 | `03_calibrate_from_polls.py` | Adjusts the model using EMC Research poll crosstabs (Feb & Sept 2026) |
| 4 | `04_build_scenarios.py` | Builds LOW/EXPECTED/HIGH scenarios for Primary and General |
| 5 | `05_aggregate.py` | Rolls up precinct estimates to Sup Districts, CD11, and Citywide |
| 6 | `06_build_dashboard.py` | Generates the interactive HTML dashboard |

## Data Sources

- **Voter file**: VAN export for CD-11 (`CD 11 Full File.xls`)
- **Historical turnout**: electionmapsf.com precinct-level data
- **Poll calibration**: EMC Research polls (Feb 2026 n=800, Sept 2025 n=500)

## Anchor Elections

| Election | Used For |
|----------|----------|
| June 2022 Primary | PRIMARY HIGH ceiling |
| March 2024 Primary | PRIMARY EXPECTED baseline |
| November 2022 General | GENERAL EXPECTED baseline |
| November 2024 General | GENERAL HIGH ceiling |

## Updating the Model

**New poll data**: Update `03_calibrate_from_polls.py` with new crosstabs, then `python run_all.py --from 3`

**Updated voter file**: Replace the input file path in `01_build_precinct_universe.py`, then `python run_all.py`

**Adjust scenarios**: Edit the scenario definitions in `04_build_scenarios.py`, then `python run_all.py --from 4`

## Output Files

All intermediate data lives in `data/processed/`:
- `precinct_universe.csv` — Voter counts by precinct and demographic group
- `historical_turnout_rates.csv` — Actual turnout by precinct for 4 anchor elections
- `demographic_turnout_rates.csv` — Estimated turnout rates by demographic group
- `calibration_weights.csv` — Poll-based calibration multipliers
- `turnout_scenarios.csv` — Precinct-level scenario estimates
- `demographic_scenarios.csv` — Demographic group scenario estimates
- `geographic_summary.csv` — Aggregated geography-level results
- `geographic_demographic_summary.csv` — Demographics by geography

## Requirements

- Python 3.8+
- pandas
- openpyxl (for reading Excel poll crosstabs)
- Internet connection (Step 2 pulls from electionmapsf.com; dashboard uses Chart.js CDN)
