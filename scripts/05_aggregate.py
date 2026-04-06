#!/usr/bin/env python3
"""
Step 5: Aggregate Precinct-Level Estimates to Geographic Summaries
===================================================================
This script rolls up the precinct-level turnout estimates (produced in Step 4)
to larger geographic levels that campaign staff actually use for planning:

  - Citywide   (all 468 SF precincts)
  - CD11       (Congressional District 11 = Sup Districts 1-10, excluding D11)
  - Sup_01 ... Sup_11  (each Board of Supervisors district)

It also breaks out the demographic composition of each geography so staff can
see, for instance, how many 18-29 year-olds are expected to vote in District 5
under the EXPECTED scenario.

Why this matters:
  Campaign decisions (field targets, mail budgets, ad buys) are made at the
  district or CD level, not the precinct level.  This script provides the
  numbers that feed directly into those decisions.

Input:  data/processed/precinct_universe.csv
        data/processed/turnout_scenarios.csv
        data/processed/demographic_scenarios.csv
        data/processed/historical_turnout_rates.csv

Output: data/processed/geographic_summary.csv
        data/processed/geographic_demographic_summary.csv

To install required packages:
    pip install pandas numpy

To run:
    python scripts/05_aggregate.py
"""

# ── Required packages ──────────────────────────────────────────────────────────
import pandas as pd
import numpy as np
import os

# ── FILE PATHS ─────────────────────────────────────────────────────────────────
# All paths are relative to the project root (one level up from scripts/).
# This lets anyone run the script from any working directory.
BASE_DIR = os.path.dirname(os.path.dirname(__file__))

# Input files (all produced by earlier pipeline steps)
PRECINCT_UNIVERSE = os.path.join(BASE_DIR, "data", "processed", "precinct_universe.csv")
TURNOUT_SCENARIOS = os.path.join(BASE_DIR, "data", "processed", "turnout_scenarios.csv")
DEMOGRAPHIC_SCENARIOS = os.path.join(BASE_DIR, "data", "processed", "demographic_scenarios.csv")
HISTORICAL_RATES = os.path.join(BASE_DIR, "data", "processed", "historical_turnout_rates.csv")

# Output files
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "processed")
OUTPUT_GEO_SUMMARY = os.path.join(OUTPUT_DIR, "geographic_summary.csv")
OUTPUT_GEO_DEMO_SUMMARY = os.path.join(OUTPUT_DIR, "geographic_demographic_summary.csv")


# ══════════════════════════════════════════════════════════════════════════════
# PART 1: LOAD ALL INPUT DATA
# ══════════════════════════════════════════════════════════════════════════════

print("=" * 70)
print("STEP 5: AGGREGATE TO GEOGRAPHIC LEVELS")
print("=" * 70)

# --- Load precinct universe ---
# This file has one row per precinct with voter counts broken out by
# demographics (age, race, party).  We need it to know the demographic
# composition of each geography.
print("\nLoading precinct universe...")
universe = pd.read_csv(PRECINCT_UNIVERSE, dtype={"PrecinctName": str})
print(f"  {len(universe)} precincts, {int(universe['total_registered'].sum()):,} total registered voters")

# --- Load turnout scenarios ---
# This is the main output of Step 4: for every precinct x election x scenario,
# it has the estimated number of ballots and turnout percentage.
print("Loading turnout scenarios...")
scenarios = pd.read_csv(TURNOUT_SCENARIOS, dtype={"PrecinctName": str})
print(f"  {len(scenarios)} rows (precincts x elections x scenarios)")

# --- Load demographic scenarios ---
# Citywide-level demographic turnout rates from Step 4.  We use these rates
# to estimate how many voters in each demographic group will turn out within
# each sub-geography.
print("Loading demographic scenarios...")
demo_scenarios = pd.read_csv(DEMOGRAPHIC_SCENARIOS)
print(f"  {len(demo_scenarios)} rows")

# --- Load historical turnout rates ---
# Actual vote counts from four real elections (Jun 2022, Mar 2024, Nov 2022,
# Nov 2024).  We use these to compute historical turnout at each geography
# so staff can compare "our estimate vs. what actually happened before."
print("Loading historical turnout rates...")
history = pd.read_csv(HISTORICAL_RATES, dtype={"PrecinctName": str})
print(f"  {len(history)} precincts")


# ══════════════════════════════════════════════════════════════════════════════
# PART 2: DEFINE GEOGRAPHIES
# ══════════════════════════════════════════════════════════════════════════════

# We want to aggregate to three levels:
#   1. "Citywide"  = ALL precincts in San Francisco
#   2. "CD11"      = Congressional District 11 = Sup Districts 1-10
#                    (District 11 is NOT in CD11 per the new boundaries)
#   3. "Sup_01" through "Sup_11" = each individual Supervisor district
#
# We build a dictionary mapping geography names to the set of precincts
# that belong to each one.  This makes the aggregation loop simple and
# consistent.

def assign_geographies(universe_df):
    """
    Build a dictionary: { geography_name -> list of PrecinctNames }.

    This is the single source of truth for which precincts belong to which
    geography.  If district boundaries change, you only need to update
    the precinct_universe.csv file -- this code adapts automatically.
    """
    geo_map = {}

    # Citywide: every precinct
    geo_map["Citywide"] = universe_df["PrecinctName"].tolist()

    # CD11: all precincts where in_cd11 == True (Sup Districts 1-10)
    cd11_mask = universe_df["in_cd11"] == True
    geo_map["CD11"] = universe_df.loc[cd11_mask, "PrecinctName"].tolist()

    # Individual Supervisor districts: Sup_01 through Sup_11
    for dist in sorted(universe_df["sup_district"].unique()):
        dist_mask = universe_df["sup_district"] == dist
        # Zero-pad to 2 digits for clean sorting (Sup_01, Sup_02, ... Sup_11)
        geo_name = f"Sup_{int(dist):02d}"
        geo_map[geo_name] = universe_df.loc[dist_mask, "PrecinctName"].tolist()

    return geo_map

geo_map = assign_geographies(universe)

print(f"\n  Geographies defined:")
for geo_name, precincts in geo_map.items():
    print(f"    {geo_name:12s}: {len(precincts):>4d} precincts")


# ══════════════════════════════════════════════════════════════════════════════
# PART 3: BUILD GEOGRAPHIC SUMMARY (geographic_summary.csv)
# ══════════════════════════════════════════════════════════════════════════════
#
# For each geography x election_type x scenario, compute:
#   - Total registered voters (sum across precincts in that geography)
#   - Total estimated ballots (sum across precincts)
#   - Estimated turnout % (ballots / registered)
#   - Historical actuals at that geography level (for comparison)
#   - Difference vs. each historical election (percentage points)
#
# Why percentage-point differences?
#   If our EXPECTED primary turnout is 42% and June 2022 was 40%, the
#   difference is +2 pp.  This tells staff whether we're projecting
#   higher or lower turnout than a real past election, which is the most
#   intuitive benchmark for campaign planning.

print("\n── BUILDING GEOGRAPHIC SUMMARY ──")

# --- Step 3a: Pre-compute historical actuals by geography ---
# For each geography, sum up the actual votes cast and the actual registered
# voters across precincts, then divide to get the turnout percentage.
#
# Important: some precincts have NaN for voted/registered in certain elections
# (e.g., a precinct that didn't exist yet in 2022).  We only include precincts
# with non-null data for that specific election.

# The four historical elections we track:
HISTORICAL_ELECTIONS = [
    {
        "label": "jun2018",
        "voted_col": "voted_primary_jun2018",
        "registered_col": "registered_primary_jun2018",
    },
    {
        "label": "jun2022",
        "voted_col": "voted_primary_jun2022",
        "registered_col": "registered_primary_jun2022",
    },
    {
        "label": "mar2024",
        "voted_col": "voted_primary_mar2024",
        "registered_col": "registered_primary_mar2024",
    },
    {
        "label": "nov2018",
        "voted_col": "voted_general_nov2018",
        "registered_col": "registered_general_nov2018",
    },
    {
        "label": "nov2022",
        "voted_col": "voted_general_nov2022",
        "registered_col": "registered_general_nov2022",
    },
    {
        "label": "nov2024",
        "voted_col": "voted_general_nov2024",
        "registered_col": "registered_general_nov2024",
    },
]

def compute_historical_turnout(history_df, precinct_list, election):
    """
    Given a list of precincts and a historical election, compute the aggregate
    turnout percentage: sum(voted) / sum(registered).

    Only includes precincts with non-null data for that election.
    Returns NaN if no precincts have data.
    """
    # Filter to precincts in this geography
    mask = history_df["PrecinctName"].isin(precinct_list)
    subset = history_df.loc[mask].copy()

    voted_col = election["voted_col"]
    reg_col = election["registered_col"]

    # Only keep rows where both voted and registered are not null
    valid = subset.dropna(subset=[voted_col, reg_col])

    if len(valid) == 0 or valid[reg_col].sum() == 0:
        return np.nan

    return valid[voted_col].sum() / valid[reg_col].sum()


# Pre-compute historical turnout for every geography
# Structure: { geography_name -> { "jun2022": 0.41, "mar2024": 0.38, ... } }
historical_by_geo = {}

for geo_name, precinct_list in geo_map.items():
    historical_by_geo[geo_name] = {}
    for election in HISTORICAL_ELECTIONS:
        rate = compute_historical_turnout(history, precinct_list, election)
        historical_by_geo[geo_name][election["label"]] = rate

print("  Historical turnout computed for all geographies.")

# --- Step 3b: Aggregate scenario estimates by geography ---

geo_summary_rows = []

for geo_name, precinct_list in geo_map.items():
    for election_type in ["primary", "general"]:
        for scenario in ["HIGH", "EXPECTED", "LOW"]:
            # Filter the precinct-level scenario data to this geography,
            # election type, and scenario
            mask = (
                scenarios["PrecinctName"].isin(precinct_list)
                & (scenarios["election_type"] == election_type)
                & (scenarios["scenario"] == scenario)
            )
            subset = scenarios.loc[mask]

            # Sum up the registered voters and estimated ballots across all
            # precincts in this geography
            registered = int(subset["registered_voters"].sum())
            ballots = int(subset["estimated_ballots"].sum())

            # Turnout % = ballots / registered (guard against division by zero
            # for any hypothetical empty geography)
            turnout_pct = ballots / registered if registered > 0 else 0.0

            # Look up the historical actuals we pre-computed
            hist = historical_by_geo[geo_name]
            hist_jun2018 = hist.get("jun2018", np.nan)
            hist_jun2022 = hist.get("jun2022", np.nan)
            hist_mar2024 = hist.get("mar2024", np.nan)
            hist_nov2018 = hist.get("nov2018", np.nan)
            hist_nov2022 = hist.get("nov2022", np.nan)
            hist_nov2024 = hist.get("nov2024", np.nan)

            # Calculate the difference (in percentage points) between our
            # scenario estimate and each historical election.
            # Example: if we estimate 42% and Jun 2022 was 40%, the diff is +2.0 pp
            def pp_diff(estimate, historical):
                """Percentage-point difference, or NaN if historical is missing."""
                if pd.isna(historical):
                    return np.nan
                return round((estimate - historical) * 100, 2)

            geo_summary_rows.append({
                "geography": geo_name,
                "election_type": election_type,
                "scenario": scenario,
                "registered_voters": registered,
                "estimated_ballots": ballots,
                "estimated_turnout_pct": round(turnout_pct, 4),
                # Historical actual turnout percentages at this geography level
                "historical_jun2018_pct": round(hist_jun2018, 4) if pd.notna(hist_jun2018) else np.nan,
                "historical_jun2022_pct": round(hist_jun2022, 4) if pd.notna(hist_jun2022) else np.nan,
                "historical_mar2024_pct": round(hist_mar2024, 4) if pd.notna(hist_mar2024) else np.nan,
                "historical_nov2018_pct": round(hist_nov2018, 4) if pd.notna(hist_nov2018) else np.nan,
                "historical_nov2022_pct": round(hist_nov2022, 4) if pd.notna(hist_nov2022) else np.nan,
                "historical_nov2024_pct": round(hist_nov2024, 4) if pd.notna(hist_nov2024) else np.nan,
                # Percentage-point differences vs. each historical election
                "vs_jun2018": pp_diff(turnout_pct, hist_jun2018),
                "vs_jun2022": pp_diff(turnout_pct, hist_jun2022),
                "vs_mar2024": pp_diff(turnout_pct, hist_mar2024),
                "vs_nov2018": pp_diff(turnout_pct, hist_nov2018),
                "vs_nov2022": pp_diff(turnout_pct, hist_nov2022),
                "vs_nov2024": pp_diff(turnout_pct, hist_nov2024),
            })

geo_summary_df = pd.DataFrame(geo_summary_rows)

print(f"  Built {len(geo_summary_df)} rows in geographic_summary.")


# ══════════════════════════════════════════════════════════════════════════════
# PART 4: BUILD GEOGRAPHIC DEMOGRAPHIC SUMMARY
#         (geographic_demographic_summary.csv)
# ══════════════════════════════════════════════════════════════════════════════
#
# This is the most complex part.  We want to know:
#   "In District 5, under the EXPECTED primary scenario, how many
#    18-29 year-olds are registered, and how many do we expect to vote?"
#
# The approach:
#   1. From precinct_universe.csv, we know how many people in each demographic
#      group live in each precinct (and therefore each geography).
#   2. From demographic_scenarios.csv, we have the CITYWIDE turnout rate for
#      each demographic group under each scenario.
#   3. We assume that the turnout rate for a demographic group is the same
#      everywhere in the city (e.g., 18-29 year-olds turn out at ~33%
#      whether they live in D1 or D8).  This is a simplification, but it's
#      the best we can do without precinct-level demographic turnout data.
#   4. For each geography, we multiply the number of people in each group
#      by the citywide turnout rate for that group to get estimated ballots.
#
# Why not use precinct-level rates?
#   We don't have turnout broken out by age/race/party at the precinct level.
#   The voter file tells us demographics per precinct, and the election
#   results tell us total turnout per precinct, but not "how many 18-29
#   year-olds voted in precinct 1101."  So we use the citywide demographic
#   rates as the best available proxy.

print("\n── BUILDING GEOGRAPHIC DEMOGRAPHIC SUMMARY ──")

# Define the demographic columns in precinct_universe.csv that correspond to
# each dimension and group in demographic_scenarios.csv.
#
# The column naming convention:
#   precinct_universe:     "age_18-29", "race_Asian", "party_Democrat"
#   demographic_scenarios: dimension="age", group="18-29"
#
# Note: age_Unknown exists in precinct_universe but NOT in demographic_scenarios.
# We skip it because the turnout model doesn't produce estimates for unknown-age
# voters (there's no meaningful turnout rate to assign to them).
DEMO_COLUMNS = {
    "age": {
        "18-29":  "age_18-29",
        "30-44":  "age_30-44",
        "45-64":  "age_45-64",
        "65+":    "age_65+",
    },
    "race": {
        "Asian":           "race_Asian",
        "Black":           "race_Black",
        "Latino/Hispanic": "race_Latino/Hispanic",
        "Other/Unknown":   "race_Other/Unknown",
        "White":           "race_White",
    },
    "party": {
        "Democrat":   "party_Democrat",
        "NPP":       "party_NPP",
        "Other":     "party_Other",
        "Republican": "party_Republican",
    },
}

# --- Step 4a: Build a lookup for citywide demographic turnout rates ---
# Structure: { (election_type, scenario, dimension, group) -> turnout_pct }
# Example key: ("primary", "EXPECTED", "age", "18-29") -> 0.331

demo_rate_lookup = {}
for _, row in demo_scenarios.iterrows():
    key = (row["election_type"], row["scenario"], row["dimension"], row["group"])
    demo_rate_lookup[key] = row["estimated_turnout_pct"]

# --- Step 4b: Pre-compute the demographic composition of each geography ---
# For each geography, sum up the count of voters in each demographic group
# across all precincts in that geography.
#
# Also compute the total registered voters in each geography (used for
# calculating pct_of_geography).

def compute_geo_demographics(universe_df, precinct_list):
    """
    For a given geography (defined by a list of precincts), compute the
    total number of registered voters in each demographic group.

    Returns a dict: { (dimension, group) -> count }
    Also returns total_registered for the geography.
    """
    mask = universe_df["PrecinctName"].isin(precinct_list)
    subset = universe_df.loc[mask]

    total_registered = int(subset["total_registered"].sum())
    group_counts = {}

    for dimension, groups in DEMO_COLUMNS.items():
        for group_name, col_name in groups.items():
            count = int(subset[col_name].sum())
            group_counts[(dimension, group_name)] = count

    return total_registered, group_counts


# Pre-compute demographics for all geographies
geo_demographics = {}
for geo_name, precinct_list in geo_map.items():
    total_reg, group_counts = compute_geo_demographics(universe, precinct_list)
    geo_demographics[geo_name] = {
        "total_registered": total_reg,
        "group_counts": group_counts,
    }

# --- Step 4c: Build the summary rows ---

geo_demo_rows = []

for geo_name, precinct_list in geo_map.items():
    geo_info = geo_demographics[geo_name]
    total_reg_in_geo = geo_info["total_registered"]
    group_counts = geo_info["group_counts"]

    for election_type in ["primary", "general"]:
        for scenario in ["HIGH", "EXPECTED", "LOW"]:
            for dimension, groups in DEMO_COLUMNS.items():
                for group_name, col_name in groups.items():
                    # How many people in this demographic group are registered
                    # in this geography?
                    registered_in_group = group_counts.get((dimension, group_name), 0)

                    # What fraction of the geography's total registration does
                    # this group represent?
                    # Example: if D5 has 40,000 voters and 8,000 are 18-29,
                    # then pct_of_geography = 0.20 (20%)
                    pct_of_geo = (
                        registered_in_group / total_reg_in_geo
                        if total_reg_in_geo > 0
                        else 0.0
                    )

                    # Look up the citywide turnout rate for this demographic
                    # group under this election/scenario combination.
                    # Example: 18-29 year-olds in EXPECTED primary turn out at 33.1%
                    rate_key = (election_type, scenario, dimension, group_name)
                    citywide_rate = demo_rate_lookup.get(rate_key, 0.0)

                    # Estimate ballots for this group in this geography:
                    # Simply multiply the number of registered voters in the
                    # group by the citywide turnout rate for that group.
                    #
                    # For very small precincts (1-2 voters), this can produce
                    # fractional ballots.  We round to the nearest integer,
                    # but keep a floor of 0 (can't have negative ballots).
                    estimated_ballots = max(0, round(registered_in_group * citywide_rate))

                    # The estimated turnout % for this group in this geography
                    # is the same as the citywide rate (our simplifying assumption).
                    # We recalculate from ballots/registered to stay internally
                    # consistent after rounding.
                    estimated_turnout_pct = (
                        estimated_ballots / registered_in_group
                        if registered_in_group > 0
                        else 0.0
                    )

                    geo_demo_rows.append({
                        "geography": geo_name,
                        "election_type": election_type,
                        "scenario": scenario,
                        "dimension": dimension,
                        "group": group_name,
                        "registered_in_group": registered_in_group,
                        "pct_of_geography": round(pct_of_geo, 4),
                        "estimated_ballots": estimated_ballots,
                        "estimated_turnout_pct": round(estimated_turnout_pct, 4),
                    })

geo_demo_df = pd.DataFrame(geo_demo_rows)

print(f"  Built {len(geo_demo_df)} rows in geographic_demographic_summary.")


# ══════════════════════════════════════════════════════════════════════════════
# PART 5: SAVE OUTPUT FILES
# ══════════════════════════════════════════════════════════════════════════════

print("\n── SAVING OUTPUTS ──")
os.makedirs(OUTPUT_DIR, exist_ok=True)

geo_summary_df.to_csv(OUTPUT_GEO_SUMMARY, index=False)
print(f"  Saved geographic summary to:             {OUTPUT_GEO_SUMMARY}")

geo_demo_df.to_csv(OUTPUT_GEO_DEMO_SUMMARY, index=False)
print(f"  Saved geographic demographic summary to: {OUTPUT_GEO_DEMO_SUMMARY}")


# ══════════════════════════════════════════════════════════════════════════════
# PART 6: PRINT SUMMARY FOR CAMPAIGN STAFF
# ══════════════════════════════════════════════════════════════════════════════
#
# This is the most-read output of the whole pipeline.  Campaign managers will
# scan this table to get the headline numbers for planning.

print("\n")
print("=" * 70)
print("  GEOGRAPHIC TURNOUT SUMMARY  --  EXPECTED SCENARIO")
print("  (This is the best estimate for campaign planning)")
print("=" * 70)

# We show only the EXPECTED scenario in the terminal printout because that's
# the number staff should use for budgeting and goal-setting.  HIGH and LOW
# are in the CSV for sensitivity analysis.

# Define a clean display order for geographies
DISPLAY_ORDER = ["Citywide", "CD11"] + [f"Sup_{d:02d}" for d in range(1, 12)]

for election_type in ["primary", "general"]:
    election_label = "JUNE 2026 PRIMARY" if election_type == "primary" else "NOVEMBER 2026 GENERAL"
    print(f"\n  ── {election_label} ──\n")
    print(f"  {'Geography':<12} {'Registered':>12} {'Est. Ballots':>14} {'Turnout %':>10}  {'vs Jun18':>8} {'vs Jun22':>8} {'vs Mar24':>8} {'vs Nov18':>8} {'vs Nov22':>8} {'vs Nov24':>8}")
    print(f"  {'-'*12:<12} {'-'*12:>12} {'-'*14:>14} {'-'*10:>10}  {'-'*8:>8} {'-'*8:>8} {'-'*8:>8} {'-'*8:>8} {'-'*8:>8} {'-'*8:>8}")

    for geo_name in DISPLAY_ORDER:
        # Pull the EXPECTED row for this geography and election type
        mask = (
            (geo_summary_df["geography"] == geo_name)
            & (geo_summary_df["election_type"] == election_type)
            & (geo_summary_df["scenario"] == "EXPECTED")
        )
        row = geo_summary_df.loc[mask]

        if row.empty:
            continue

        row = row.iloc[0]
        registered = row["registered_voters"]
        ballots = row["estimated_ballots"]
        turnout = row["estimated_turnout_pct"]

        # Format the vs-historical columns as "+2.3" or "-1.5" percentage points
        def fmt_diff(val):
            """Format a percentage-point difference for display."""
            if pd.isna(val):
                return "    --"
            sign = "+" if val >= 0 else ""
            return f"{sign}{val:5.1f}pp"

        vs_jun18 = fmt_diff(row["vs_jun2018"])
        vs_jun22 = fmt_diff(row["vs_jun2022"])
        vs_mar24 = fmt_diff(row["vs_mar2024"])
        vs_nov18 = fmt_diff(row["vs_nov2018"])
        vs_nov22 = fmt_diff(row["vs_nov2022"])
        vs_nov24 = fmt_diff(row["vs_nov2024"])

        print(
            f"  {geo_name:<12} {registered:>12,} {ballots:>14,} {turnout:>9.1%}"
            f"  {vs_jun18:>8} {vs_jun22:>8} {vs_mar24:>8} {vs_nov18:>8} {vs_nov22:>8} {vs_nov24:>8}"
        )

    # Add a blank line between primary and general
    print()

# --- Also show the LOW and HIGH bounds for Citywide and CD11 ---
print("\n" + "-" * 70)
print("  SCENARIO RANGES (LOW / EXPECTED / HIGH)")
print("-" * 70)
print(f"\n  {'Geography':<12} {'Election':<18} {'Scenario':<10} {'Registered':>12} {'Est. Ballots':>14} {'Turnout %':>10}")
print(f"  {'-'*12:<12} {'-'*18:<18} {'-'*10:<10} {'-'*12:>12} {'-'*14:>14} {'-'*10:>10}")

for geo_name in ["Citywide", "CD11"]:
    for election_type in ["primary", "general"]:
        election_label = "Jun 2026 Primary" if election_type == "primary" else "Nov 2026 General"
        for scenario in ["LOW", "EXPECTED", "HIGH"]:
            mask = (
                (geo_summary_df["geography"] == geo_name)
                & (geo_summary_df["election_type"] == election_type)
                & (geo_summary_df["scenario"] == scenario)
            )
            row = geo_summary_df.loc[mask]
            if row.empty:
                continue
            row = row.iloc[0]

            print(
                f"  {geo_name:<12} {election_label:<18} {scenario:<10}"
                f" {row['registered_voters']:>12,} {row['estimated_ballots']:>14,}"
                f" {row['estimated_turnout_pct']:>9.1%}"
            )

# --- Demographic highlights for CD11 EXPECTED ---
print("\n\n" + "-" * 70)
print("  CD11 DEMOGRAPHIC HIGHLIGHTS  --  EXPECTED SCENARIO")
print("-" * 70)

for election_type in ["primary", "general"]:
    election_label = "JUNE 2026 PRIMARY" if election_type == "primary" else "NOVEMBER 2026 GENERAL"
    print(f"\n  ── {election_label} ──\n")

    for dimension in ["age", "race", "party"]:
        # Get the CD11 demographic data for this election/scenario
        mask = (
            (geo_demo_df["geography"] == "CD11")
            & (geo_demo_df["election_type"] == election_type)
            & (geo_demo_df["scenario"] == "EXPECTED")
            & (geo_demo_df["dimension"] == dimension)
        )
        subset = geo_demo_df.loc[mask].copy()

        if subset.empty:
            continue

        print(f"    {dimension.upper()}")
        print(f"    {'Group':<20} {'Registered':>12} {'% of CD11':>10} {'Est. Ballots':>14} {'Turnout %':>10}")
        print(f"    {'-'*20:<20} {'-'*12:>12} {'-'*10:>10} {'-'*14:>14} {'-'*10:>10}")

        for _, drow in subset.iterrows():
            print(
                f"    {drow['group']:<20}"
                f" {drow['registered_in_group']:>12,}"
                f" {drow['pct_of_geography']:>9.1%}"
                f" {drow['estimated_ballots']:>14,}"
                f" {drow['estimated_turnout_pct']:>9.1%}"
            )
        print()

print("\n" + "=" * 70)
print("STEP 5 COMPLETE")
print("=" * 70)
print(f"\nOutput files:")
print(f"  {OUTPUT_GEO_SUMMARY}")
print(f"  {OUTPUT_GEO_DEMO_SUMMARY}")
print()
