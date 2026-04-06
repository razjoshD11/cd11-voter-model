#!/usr/bin/env python3
"""
Step 2: Calculate Historical Turnout Rates
============================================
Pulls precinct-level turnout data from electionmapsf.com for all four anchor
elections, then calculates turnout rates per precinct. Also estimates
demographic-level turnout rates by combining precinct demographics (Step 1)
with precinct turnout.

Input:  electionmapsf.com API + data/processed/precinct_universe.csv
Output: data/processed/historical_turnout_rates.csv
        data/processed/demographic_turnout_rates.csv

To install required packages:
    pip install pandas numpy requests

To run:
    python scripts/02_calculate_historical_rates.py
"""

# ── Required packages ──────────────────────────────────────────────────────────
import pandas as pd
import numpy as np
import json
import os
import sys

import subprocess

def fetch_json(url):
    """Download JSON from a URL using curl (most reliable for this API)."""
    result = subprocess.run(
        ["curl", "-s", "-f", url],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl failed for {url}: {result.stderr}")
    return json.loads(result.stdout)

# ── FILE PATHS ─────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PRECINCT_UNIVERSE = os.path.join(BASE_DIR, "data", "processed", "precinct_universe.csv")
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "processed")
OUTPUT_TURNOUT = os.path.join(OUTPUT_DIR, "historical_turnout_rates.csv")
OUTPUT_DEMO_RATES = os.path.join(OUTPUT_DIR, "demographic_turnout_rates.csv")

# Historical Turnout spreadsheet (for validation)
HISTORICAL_SPREADSHEET = "/Users/joshraznick/Downloads/Historical Turnout.xlsx"

# ── ANCHOR ELECTIONS ───────────────────────────────────────────────────────────
# These are the four real elections the model is calibrated against.
# The API date is the actual election date used in the electionmapsf.com URL.
ANCHOR_ELECTIONS = {
    "primary_jun2018": {
        "label": "June 2018 Primary",
        "api_date": "2018-06-05",
        "type": "primary",
    },
    "primary_jun2022": {
        "label": "June 2022 Primary",
        "api_date": "2022-06-07",
        "type": "primary",
    },
    "primary_mar2024": {
        "label": "March 2024 Primary",
        "api_date": "2024-03-05",
        "type": "primary",
    },
    "general_nov2018": {
        "label": "November 2018 General",
        "api_date": "2018-11-06",
        "type": "general",
    },
    "general_nov2022": {
        "label": "November 2022 General",
        "api_date": "2022-11-08",
        "type": "general",
    },
    "general_nov2024": {
        "label": "November 2024 General",
        "api_date": "2024-11-05",
        "type": "general",
    },
}

# Base URL for the electionmapsf.com data API
API_BASE = "https://data.electionmapsf.com/prod/san_francisco"

# ── STEP 2A: Load precinct universe from Step 1 ──────────────────────────────
print("=" * 70)
print("STEP 2: CALCULATE HISTORICAL TURNOUT RATES")
print("=" * 70)

print(f"\nLoading precinct universe from: {PRECINCT_UNIVERSE}")
universe = pd.read_csv(PRECINCT_UNIVERSE, dtype={"PrecinctName": str})
print(f"  Loaded {len(universe)} precincts, {int(universe['total_registered'].sum()):,} total voters")

# ── STEP 2B: Pull precinct-level turnout from electionmapsf.com ──────────────
print("\n── PULLING TURNOUT DATA FROM electionmapsf.com ──")

# We'll collect turnout data for all elections into one dictionary
# Structure: { precinct_id: { "turnout_jun2022": float, "turnout_mar2024": float, ... } }
all_election_data = {}

for election_key, election_info in ANCHOR_ELECTIONS.items():
    url = f"{API_BASE}/{election_info['api_date']}/results.json"
    print(f"\n  Fetching {election_info['label']} ({election_info['api_date']})...")
    print(f"    URL: {url}")

    data = fetch_json(url)

    # Extract precinct-level turnout
    precincts = data["resultsByView"]["precinct"]
    print(f"    Found {len(precincts)} precincts in election data")

    # Accumulate totals for validation
    total_registered = 0
    total_voted = 0

    for precinct_id, precinct_data in precincts.items():
        turnout = precinct_data.get("turnout", {})
        registered = turnout.get("registered", 0)
        voted = turnout.get("voted", 0)

        total_registered += registered
        total_voted += voted

        # Store this election's data for this precinct
        if precinct_id not in all_election_data:
            all_election_data[precinct_id] = {}

        # Calculate turnout rate; avoid division by zero
        rate = voted / registered if registered > 0 else 0.0
        all_election_data[precinct_id][f"turnout_{election_key}"] = rate
        all_election_data[precinct_id][f"voted_{election_key}"] = voted
        all_election_data[precinct_id][f"registered_{election_key}"] = registered

    # Print validation totals
    overall_rate = total_voted / total_registered if total_registered > 0 else 0
    print(f"    Total registered: {total_registered:,}")
    print(f"    Total voted:      {total_voted:,}")
    print(f"    Overall turnout:  {overall_rate:.1%}")

# Convert to DataFrame
turnout_df = pd.DataFrame.from_dict(all_election_data, orient="index")
turnout_df.index.name = "PrecinctName"
turnout_df = turnout_df.reset_index()

print(f"\n  Combined turnout data: {len(turnout_df)} precincts across all elections")

# ── STEP 2C: Validate against Historical Turnout spreadsheet ─────────────────
print("\n── VALIDATING AGAINST HISTORICAL SPREADSHEET ──")

# Known citywide totals from the spreadsheet
KNOWN_TOTALS = {
    "primary_jun2018":  {"registered": 479054, "voted": 222413},
    "primary_jun2022":  {"registered": 495498, "voted": 229229},
    "primary_mar2024":  {"registered": 500856, "voted": 233465},
    "general_nov2018":  {"registered": 488541, "voted": 339653},
    "general_nov2022":  {"registered": 497561, "voted": 310071},
    "general_nov2024":  {"registered": 522265, "voted": 412231},
}

for election_key, known in KNOWN_TOTALS.items():
    reg_col = f"registered_{election_key}"
    voted_col = f"voted_{election_key}"

    if reg_col in turnout_df.columns:
        api_registered = int(turnout_df[reg_col].sum())
        api_voted = int(turnout_df[voted_col].sum())

        reg_diff = abs(api_registered - known["registered"])
        voted_diff = abs(api_voted - known["voted"])

        label = ANCHOR_ELECTIONS[election_key]["label"]
        reg_match = "MATCH" if reg_diff == 0 else f"DIFF: {reg_diff:,}"
        voted_match = "MATCH" if voted_diff == 0 else f"DIFF: {voted_diff:,}"

        print(f"  {label}:")
        print(f"    Registered — API: {api_registered:,} | Spreadsheet: {known['registered']:,} | {reg_match}")
        print(f"    Voted      — API: {api_voted:,} | Spreadsheet: {known['voted']:,} | {voted_match}")

# ── STEP 2D: Match precincts between voter file and election data ─────────────
print("\n── PRECINCT MATCHING ──")

voter_precincts = set(universe["PrecinctName"].unique())
election_precincts = set(turnout_df["PrecinctName"].unique())

overlap = voter_precincts & election_precincts
only_voter = voter_precincts - election_precincts
only_election = election_precincts - voter_precincts

print(f"  Voter file precincts:     {len(voter_precincts)}")
print(f"  Election data precincts:  {len(election_precincts)}")
print(f"  Overlapping:              {len(overlap)}")
print(f"  In voter file only:       {len(only_voter)}")
print(f"  In election data only:    {len(only_election)}")

if only_voter:
    print(f"\n  Voter-file-only precincts (no election data — likely data errors):")
    for p in sorted(only_voter):
        n_voters = int(universe.loc[universe["PrecinctName"] == p, "total_registered"].values[0])
        print(f"    {p}: {n_voters} registered voters")

if only_election:
    print(f"\n  Election-data-only precincts (no current voters — likely boundary changes):")
    # Only show first 10
    shown = sorted(only_election)[:10]
    for p in shown:
        print(f"    {p}")
    if len(only_election) > 10:
        print(f"    ... and {len(only_election) - 10} more")

# ── STEP 2E: Handle 2022 precinct boundary changes ───────────────────────────
print("\n── PRECINCT BOUNDARY CHANGES (2022 → 2024) ──")

# June 2022 used the old precinct map (613 precincts).
# 2024 elections use the new map (~514 precincts).
# We need to identify 2022-only precincts and handle them.

# Get precincts that appear in the 2022 elections but not 2024
reg_2022_col = "registered_primary_jun2022"
reg_2024_col = "registered_primary_mar2024"

precincts_with_2022 = set(turnout_df.loc[turnout_df[reg_2022_col] > 0, "PrecinctName"])
precincts_with_2024 = set(turnout_df.loc[turnout_df[reg_2024_col] > 0, "PrecinctName"])

only_2022 = precincts_with_2022 - precincts_with_2024
only_2024 = precincts_with_2024 - precincts_with_2022
both = precincts_with_2022 & precincts_with_2024

print(f"  Precincts in 2022 data only: {len(only_2022)} (old boundary map)")
print(f"  Precincts in 2024 data only: {len(only_2024)} (new boundary map)")
print(f"  Precincts in both:           {len(both)}")

# For precincts that only exist in the 2022 map, we cannot directly use their
# turnout rates for 2024-era precincts. For these old-map precincts, we assign
# the CITYWIDE turnout rate for 2022 elections as a fallback. This is documented
# as an approximation.
citywide_turnout_jun2018 = 222413 / 479054  # 46.4%
citywide_turnout_jun2022 = 229229 / 495498  # 46.3%
citywide_turnout_nov2018 = 339653 / 488541  # 69.5%
citywide_turnout_nov2022 = 310071 / 497561  # 62.3%

print(f"\n  For old-map precincts, using citywide fallback rates:")
print(f"    June 2018 Primary:     {citywide_turnout_jun2018:.1%}")
print(f"    June 2022 Primary:     {citywide_turnout_jun2022:.1%}")
print(f"    November 2018 General: {citywide_turnout_nov2018:.1%}")
print(f"    November 2022 General: {citywide_turnout_nov2022:.1%}")

# ── STEP 2F: Merge turnout with precinct universe ────────────────────────────
print("\n── MERGING TURNOUT WITH PRECINCT UNIVERSE ──")

# Left join: keep all voter file precincts, add turnout data where available
merged = universe.merge(turnout_df, on="PrecinctName", how="left")

# For matching precincts, turnout columns will have values.
# For voter-file-only precincts, turnout columns will be NaN.

# Fill missing 2024-era turnout with NaN (these precincts need manual review)
# Fill missing 2022-era turnout with citywide average for those voter-file precincts
# that exist in the current map but weren't in the old 2022 map
for election_key in ANCHOR_ELECTIONS:
    turnout_col = f"turnout_{election_key}"
    if turnout_col in merged.columns:
        n_missing = merged[turnout_col].isna().sum()
        if n_missing > 0:
            # Use citywide average as fallback
            if "jun2018" in election_key:
                merged[turnout_col] = merged[turnout_col].fillna(citywide_turnout_jun2018)
            elif "jun2022" in election_key:
                merged[turnout_col] = merged[turnout_col].fillna(citywide_turnout_jun2022)
            elif "nov2018" in election_key:
                merged[turnout_col] = merged[turnout_col].fillna(citywide_turnout_nov2018)
            elif "nov2022" in election_key:
                merged[turnout_col] = merged[turnout_col].fillna(citywide_turnout_nov2022)
            else:
                # For 2024 elections, fill with citywide average
                avg = merged[turnout_col].mean()
                merged[turnout_col] = merged[turnout_col].fillna(avg)
            print(f"  {turnout_col}: filled {n_missing} missing precincts with fallback")

# ── STEP 2G: Estimate demographic-level turnout rates ─────────────────────────
print("\n── ESTIMATING DEMOGRAPHIC TURNOUT RATES ──")
print("  (Approximation: assumes uniform turnout within each precinct across demographics)")
print("  (In reality, different groups vote at different rates — this is why we calibrate in Step 3)")

# The approach: For each demographic group, calculate a weighted-average turnout
# rate across all precincts, where the weight is the number of voters in that
# demographic group in each precinct.
#
# If a precinct has 60% turnout and 500 Democratic voters, those 500 Democrats
# are assigned a 60% turnout rate. Averaging across all precincts, we get an
# estimate of Democratic turnout that accounts for where Democrats live.

demo_groups = {
    "age": ["age_18-29", "age_30-44", "age_45-64", "age_65+"],
    "race": ["race_Asian", "race_Black", "race_Latino/Hispanic", "race_White", "race_Other/Unknown"],
    "party": ["party_Democrat", "party_NPP", "party_Other", "party_Republican"],
}

demo_rates_rows = []

for dimension, groups in demo_groups.items():
    for group_col in groups:
        group_name = group_col.split("_", 1)[1]  # e.g., "18-29", "Democrat"

        for election_key in ANCHOR_ELECTIONS:
            turnout_col = f"turnout_{election_key}"
            label = ANCHOR_ELECTIONS[election_key]["label"]

            # Weighted average: sum(group_count * turnout) / sum(group_count)
            # Only use precincts where we have both voter data and turnout data
            mask = merged[group_col] > 0
            if mask.sum() == 0:
                continue

            weighted_sum = (merged.loc[mask, group_col] * merged.loc[mask, turnout_col]).sum()
            total_count = merged.loc[mask, group_col].sum()
            estimated_rate = weighted_sum / total_count if total_count > 0 else 0

            demo_rates_rows.append({
                "dimension": dimension,
                "group": group_name,
                "election": election_key,
                "election_label": label,
                "estimated_turnout_rate": round(estimated_rate, 4),
                "total_voters_in_group": int(total_count),
            })

demo_rates_df = pd.DataFrame(demo_rates_rows)

# Print summary table
print("\n  Estimated Demographic Turnout Rates (precinct-weighted):\n")
for dimension in ["age", "race", "party"]:
    print(f"  {dimension.upper()}")
    subset = demo_rates_df[demo_rates_df["dimension"] == dimension]
    # Pivot for display
    pivot = subset.pivot(index="group", columns="election_label", values="estimated_turnout_rate")
    # Reorder columns
    col_order = [e["label"] for e in ANCHOR_ELECTIONS.values() if e["label"] in pivot.columns]
    pivot = pivot[col_order]
    for idx, row in pivot.iterrows():
        vals = "  ".join(f"{v:.1%}" for v in row.values)
        print(f"    {idx:20s}  {vals}")
    print()

# ── STEP 2H: Flag registration drift ─────────────────────────────────────────
print("── REGISTRATION DRIFT CHECK ──")
print("  Comparing current voter file registration to 2022 election registration...")

reg_col_2022 = "registered_general_nov2022"
if reg_col_2022 in merged.columns:
    # Only check precincts that exist in both datasets
    check = merged[merged[reg_col_2022] > 0].copy()
    check["reg_change_pct"] = (check["total_registered"] - check[reg_col_2022]) / check[reg_col_2022]

    big_growth = check[check["reg_change_pct"] > 0.20]
    big_shrink = check[check["reg_change_pct"] < -0.20]

    print(f"  Precincts with >20% growth since Nov 2022:  {len(big_growth)}")
    print(f"  Precincts with >20% shrinkage since Nov 2022: {len(big_shrink)}")
    if len(big_growth) > 0:
        print("    (These precincts' historical rates may be less reliable)")
        for _, row in big_growth.head(5).iterrows():
            print(f"    Precinct {row['PrecinctName']}: {row[reg_col_2022]:.0f} → {row['total_registered']:.0f} ({row['reg_change_pct']:+.0%})")

# ── STEP 2I: Save outputs ────────────────────────────────────────────────────
print("\n── SAVING OUTPUTS ──")

# Save the main turnout rates file (one row per precinct)
output_cols = ["PrecinctName", "sup_district", "in_cd11"]
for election_key in ANCHOR_ELECTIONS:
    output_cols.append(f"turnout_{election_key}")
    output_cols.append(f"voted_{election_key}")
    output_cols.append(f"registered_{election_key}")

# Only keep columns that exist
output_cols = [c for c in output_cols if c in merged.columns]
turnout_output = merged[output_cols].copy()

turnout_output.to_csv(OUTPUT_TURNOUT, index=False)
print(f"  Saved precinct turnout rates to: {OUTPUT_TURNOUT}")

# Save demographic rates
demo_rates_df.to_csv(OUTPUT_DEMO_RATES, index=False)
print(f"  Saved demographic turnout rates to: {OUTPUT_DEMO_RATES}")

print(f"\n── SUMMARY ──")
print(f"  Precincts with turnout data: {len(turnout_output)}")
print(f"  Anchor elections processed:  {len(ANCHOR_ELECTIONS)}")
print(f"  Demographic rate estimates:  {len(demo_rates_df)} (groups x elections)")

print("\n" + "=" * 70)
print("STEP 2 COMPLETE")
print("=" * 70)
