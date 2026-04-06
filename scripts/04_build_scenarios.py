#!/usr/bin/env python3
"""
Step 4: Build Three Scenarios (Primary + General)
===================================================
Combines precinct-level historical turnout rates with calibration multipliers
to produce LOW, EXPECTED, and HIGH turnout estimates for:
  - June 2026 Primary (3 scenarios)
  - November 2026 General (3 scenarios)

Each scenario anchors to a specific real election rather than a flat percentage.

Input:  data/processed/precinct_universe.csv
        data/processed/historical_turnout_rates.csv
        data/processed/calibration_weights.csv

Output: data/processed/turnout_scenarios.csv
        data/processed/demographic_scenarios.csv

To install required packages:
    pip install pandas numpy

To run:
    python scripts/04_build_scenarios.py
"""

# ── Required packages ──────────────────────────────────────────────────────────
import pandas as pd
import numpy as np
import os

# ── FILE PATHS ─────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PRECINCT_UNIVERSE = os.path.join(BASE_DIR, "data", "processed", "precinct_universe.csv")
HISTORICAL_RATES = os.path.join(BASE_DIR, "data", "processed", "historical_turnout_rates.csv")
CALIBRATION_WEIGHTS = os.path.join(BASE_DIR, "data", "processed", "calibration_weights.csv")
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "processed")
OUTPUT_SCENARIOS = os.path.join(OUTPUT_DIR, "turnout_scenarios.csv")
OUTPUT_DEMO_SCENARIOS = os.path.join(OUTPUT_DIR, "demographic_scenarios.csv")

# ── LOAD DATA ──────────────────────────────────────────────────────────────────
print("=" * 70)
print("STEP 4: BUILD THREE SCENARIOS")
print("=" * 70)

print("\nLoading precinct universe...")
universe = pd.read_csv(PRECINCT_UNIVERSE, dtype={"PrecinctName": str})
print(f"  {len(universe)} precincts, {int(universe['total_registered'].sum()):,} voters")

print("Loading historical turnout rates...")
history = pd.read_csv(HISTORICAL_RATES, dtype={"PrecinctName": str})
print(f"  {len(history)} precincts")

print("Loading calibration weights...")
cal = pd.read_csv(CALIBRATION_WEIGHTS)
print(f"  {len(cal)} multipliers")

# Build a lookup dict for calibration multipliers
# Key: (dimension, group) -> multiplier
cal_lookup = {}
for _, row in cal.iterrows():
    m = row["calibration_multiplier"]
    # Cap suspect multipliers at 2.0 and floor at 0.5
    m = max(0.5, min(2.0, m))
    cal_lookup[(row["dimension"], row["group"])] = m

print("\n  Calibration multipliers (capped 0.5–2.0):")
for (dim, grp), m in sorted(cal_lookup.items()):
    print(f"    {dim:6s} | {grp:20s}: {m:.3f}")

# Merge universe with historical turnout
merged = universe.merge(history, on="PrecinctName", how="left", suffixes=("", "_hist"))

# Drop duplicate columns from merge
for col in merged.columns:
    if col.endswith("_hist"):
        merged = merged.drop(columns=[col])

# ── HELPER: Calculate combined calibration multiplier for a precinct ──────────
def precinct_calibration_multiplier(row, total_reg):
    """
    Calculate a blended calibration multiplier for a precinct based on its
    demographic composition. We average the age, race, and party multipliers,
    weighted by the number of voters in each group.

    The three dimensions (age, race, party) are averaged with equal weight
    to avoid over-counting (since every voter belongs to one group in each
    dimension).
    """
    if total_reg == 0:
        return 1.0

    # Calculate weighted average multiplier for each dimension separately
    dim_multipliers = []

    for dim, prefix_cols in [
        ("age", ["age_18-29", "age_30-44", "age_45-64", "age_65+"]),
        ("race", ["race_Asian", "race_Black", "race_Latino/Hispanic", "race_White", "race_Other/Unknown"]),
        ("party", ["party_Democrat", "party_NPP", "party_Other", "party_Republican"]),
    ]:
        weighted_sum = 0.0
        dim_total = 0.0
        for col in prefix_cols:
            if col not in row.index:
                continue
            grp = col.split("_", 1)[1]
            count = row[col]
            m = cal_lookup.get((dim, grp), 1.0)
            weighted_sum += count * m
            dim_total += count

        if dim_total > 0:
            dim_multipliers.append(weighted_sum / dim_total)
        else:
            dim_multipliers.append(1.0)

    # Average across dimensions (equal weight)
    return np.mean(dim_multipliers)


# ── BUILD SCENARIOS ───────────────────────────────────────────────────────────

# Define the six scenarios with their anchor elections and parameters
SCENARIOS = {
    # ── JUNE 2026 PRIMARY ──
    "primary_high": {
        "election_type": "primary",
        "scenario": "HIGH",
        "anchor": "June 2022 Primary",
        "base_col": "turnout_primary_jun2022",
        "cap_col": "turnout_primary_jun2022",  # cannot exceed actual Jun 2022
        "blend": None,  # pure anchor (no weighted average)
        "reduction": 0.0,
        "description": "Anchor: June 2022 Primary (high-engagement primary with Pelosi/Newsom on ballot)",
    },
    "primary_expected": {
        "election_type": "primary",
        "scenario": "EXPECTED",
        "anchor": "40% Jun 2022 + 60% Mar 2024",
        "base_col": None,  # computed from blend
        "blend": [("turnout_primary_jun2022", 0.40), ("turnout_primary_mar2024", 0.60)],
        "cap_col": None,
        "reduction": 0.0,
        "description": "Weighted avg: 40% June 2022 + 60% March 2024 (structural analog)",
    },
    "primary_low": {
        "election_type": "primary",
        "scenario": "LOW",
        "anchor": "March 2024 Primary - 10%",
        "base_col": "turnout_primary_mar2024",
        "cap_col": None,
        "reduction": 0.10,  # 10% additional reduction
        "description": "Anchor: March 2024 Primary with 10% reduction (low-enthusiasm scenario)",
    },

    # ── NOVEMBER 2026 GENERAL ──
    "general_high": {
        "election_type": "general",
        "scenario": "HIGH",
        "anchor": "November 2024 General",
        "base_col": "turnout_general_nov2024",
        "cap_col": "turnout_general_nov2024",  # cannot exceed actual Nov 2024
        "reduction": 0.0,
        "description": "Anchor: November 2024 General (presidential, peak anti-Trump motivation)",
    },
    "general_expected": {
        "election_type": "general",
        "scenario": "EXPECTED",
        "anchor": "60% Nov 2022 + 40% Nov 2024",
        "base_col": None,
        "blend": [("turnout_general_nov2022", 0.60), ("turnout_general_nov2024", 0.40)],
        "cap_col": None,
        "reduction": 0.0,
        "description": "Weighted avg: 60% Nov 2022 + 40% Nov 2024 (midterm-like environment)",
    },
    "general_low": {
        "election_type": "general",
        "scenario": "LOW",
        "anchor": "November 2022 General - 10%",
        "base_col": "turnout_general_nov2022",
        "cap_col": None,
        "reduction": 0.10,
        "description": "Anchor: November 2022 General with 10% reduction (low-enthusiasm midterm)",
    },
}

# Find the floor rate per precinct (lowest observed turnout since 2018)
# We have 6 elections; use the minimum across all available
turnout_cols = [c for c in merged.columns if c.startswith("turnout_")]
if turnout_cols:
    primary_floor_cols = [c for c in ["turnout_primary_jun2018", "turnout_primary_jun2022", "turnout_primary_mar2024"] if c in merged.columns]
    general_floor_cols = [c for c in ["turnout_general_nov2018", "turnout_general_nov2022", "turnout_general_nov2024"] if c in merged.columns]
    merged["floor_primary"] = merged[primary_floor_cols].min(axis=1)
    merged["floor_general"] = merged[general_floor_cols].min(axis=1)

# ── Calculate calibration multiplier per precinct ─────────────────────────────
print("\n── CALCULATING PRECINCT-LEVEL CALIBRATION MULTIPLIERS ──")
merged["cal_multiplier"] = merged.apply(
    lambda row: precinct_calibration_multiplier(row, row["total_registered"]),
    axis=1,
)
print(f"  Mean calibration multiplier: {merged['cal_multiplier'].mean():.3f}")
print(f"  Range: {merged['cal_multiplier'].min():.3f} – {merged['cal_multiplier'].max():.3f}")

# ── Build scenario estimates ──────────────────────────────────────────────────
print("\n── BUILDING SCENARIO ESTIMATES ──")

scenario_rows = []

for scenario_key, params in SCENARIOS.items():
    print(f"\n  {params['election_type'].upper()} {params['scenario']}: {params['description']}")

    for _, row in merged.iterrows():
        precinct = row["PrecinctName"]
        registered = row["total_registered"]

        # Step 1: Get the base turnout rate for this precinct
        if params.get("blend"):
            # Weighted average of multiple anchor elections
            base_rate = sum(
                row[col] * weight for col, weight in params["blend"]
                if col in row.index and pd.notna(row[col])
            )
        else:
            base_rate = row.get(params["base_col"], 0)
            if pd.isna(base_rate):
                base_rate = 0

        # Step 2: Apply the 10% reduction (for LOW scenarios)
        base_rate = base_rate * (1.0 - params["reduction"])

        # Step 3: Apply calibration multiplier
        calibrated_rate = base_rate * row["cal_multiplier"]

        # Step 4: Apply cap (for HIGH scenarios — cannot exceed historical actual)
        if params["cap_col"] and params["cap_col"] in row.index:
            cap_val = row[params["cap_col"]]
            if pd.notna(cap_val):
                calibrated_rate = min(calibrated_rate, cap_val)

        # Step 5: Apply floor (cannot go below the lowest observed turnout)
        if params["election_type"] == "primary":
            floor_val = row.get("floor_primary", 0)
        else:
            floor_val = row.get("floor_general", 0)

        if pd.notna(floor_val) and floor_val > 0:
            calibrated_rate = max(calibrated_rate, floor_val)

        # Step 6: Clamp between 0 and 1
        calibrated_rate = max(0.0, min(1.0, calibrated_rate))

        # Calculate estimated ballots
        estimated_ballots = round(registered * calibrated_rate)

        scenario_rows.append({
            "PrecinctName": precinct,
            "sup_district": row["sup_district"],
            "in_cd11": row["in_cd11"],
            "election_type": params["election_type"],
            "scenario": params["scenario"],
            "registered_voters": int(registered),
            "estimated_ballots": int(estimated_ballots),
            "estimated_turnout_pct": round(calibrated_rate, 4),
            "anchor_election": params["anchor"],
            "calibration_applied": round(row["cal_multiplier"], 4),
        })

    # Print quick summary for this scenario
    scenario_subset = [r for r in scenario_rows if
        r["scenario"] == params["scenario"] and
        r["election_type"] == params["election_type"]]
    total_reg = sum(r["registered_voters"] for r in scenario_subset)
    total_ballots = sum(r["estimated_ballots"] for r in scenario_subset)
    avg_turnout = total_ballots / total_reg if total_reg > 0 else 0
    print(f"    Citywide: {total_ballots:,} ballots / {total_reg:,} registered = {avg_turnout:.1%}")

scenarios_df = pd.DataFrame(scenario_rows)

# ── BUILD DEMOGRAPHIC SCENARIO ESTIMATES ──────────────────────────────────────
print("\n── BUILDING DEMOGRAPHIC SCENARIO ESTIMATES ──")

# For each scenario, estimate turnout by demographic group at the citywide/CD11 level.
# Method: Apply the scenario's precinct-level rate to each demographic group within
# each precinct, weighted by the group's count in that precinct.

demo_scenario_rows = []

demo_groups = {
    "age": ["age_18-29", "age_30-44", "age_45-64", "age_65+"],
    "race": ["race_Asian", "race_Black", "race_Latino/Hispanic", "race_White", "race_Other/Unknown"],
    "party": ["party_Democrat", "party_NPP", "party_Other", "party_Republican"],
}

for scenario_key, params in SCENARIOS.items():
    # Get the scenario rates from scenarios_df
    scenario_subset = scenarios_df[
        (scenarios_df["scenario"] == params["scenario"]) &
        (scenarios_df["election_type"] == params["election_type"])
    ].set_index("PrecinctName")

    for dimension, cols in demo_groups.items():
        for col in cols:
            group_name = col.split("_", 1)[1]

            # For each precinct, multiply group count by scenario turnout rate
            total_group_voters = 0
            total_group_ballots = 0

            for _, row in merged.iterrows():
                precinct = row["PrecinctName"]
                group_count = row.get(col, 0)
                if precinct in scenario_subset.index:
                    rate = scenario_subset.loc[precinct, "estimated_turnout_pct"]
                else:
                    rate = 0

                # Apply group-specific calibration on top of precinct rate
                # The precinct rate already has the blended calibration.
                # For demographic breakdowns, we also apply the group-specific
                # multiplier relative to the precinct average, to differentiate
                # within-precinct turnout.
                group_multiplier = cal_lookup.get((dimension, group_name), 1.0)
                precinct_avg_multiplier = row.get("cal_multiplier", 1.0)

                if precinct_avg_multiplier > 0:
                    relative_multiplier = group_multiplier / precinct_avg_multiplier
                else:
                    relative_multiplier = 1.0

                adjusted_rate = min(1.0, max(0.0, rate * relative_multiplier))
                est_ballots = group_count * adjusted_rate

                total_group_voters += group_count
                total_group_ballots += est_ballots

            group_rate = total_group_ballots / total_group_voters if total_group_voters > 0 else 0

            demo_scenario_rows.append({
                "election_type": params["election_type"],
                "scenario": params["scenario"],
                "dimension": dimension,
                "group": group_name,
                "total_registered": int(total_group_voters),
                "estimated_ballots": int(round(total_group_ballots)),
                "estimated_turnout_pct": round(group_rate, 4),
            })

demo_scenarios_df = pd.DataFrame(demo_scenario_rows)

# Print demographic summaries
for election_type in ["primary", "general"]:
    print(f"\n  {election_type.upper()} Demographic Turnout Estimates:")
    for dimension in ["age", "race", "party"]:
        subset = demo_scenarios_df[
            (demo_scenarios_df["election_type"] == election_type) &
            (demo_scenarios_df["dimension"] == dimension)
        ]
        pivot = subset.pivot(index="group", columns="scenario", values="estimated_turnout_pct")
        if "LOW" in pivot.columns and "EXPECTED" in pivot.columns and "HIGH" in pivot.columns:
            pivot = pivot[["LOW", "EXPECTED", "HIGH"]]

        print(f"    {dimension.upper()}")
        for idx, row_data in pivot.iterrows():
            vals = "  ".join(f"{v:.1%}" for v in row_data.values)
            print(f"      {idx:20s}  {vals}")

# ── SAVE OUTPUTS ──────────────────────────────────────────────────────────────
print("\n── SAVING OUTPUTS ──")

os.makedirs(OUTPUT_DIR, exist_ok=True)
scenarios_df.to_csv(OUTPUT_SCENARIOS, index=False)
print(f"  Saved precinct scenarios to: {OUTPUT_SCENARIOS}")

demo_scenarios_df.to_csv(OUTPUT_DEMO_SCENARIOS, index=False)
print(f"  Saved demographic scenarios to: {OUTPUT_DEMO_SCENARIOS}")

# ── SUMMARY TABLE ─────────────────────────────────────────────────────────────
print("\n── SUMMARY: CITYWIDE SCENARIO ESTIMATES ──\n")
print(f"  {'Election':<20} {'Scenario':<10} {'Registered':>12} {'Est. Ballots':>14} {'Turnout':>8}")
print(f"  {'-'*20:<20} {'-'*10:<10} {'-'*12:>12} {'-'*14:>14} {'-'*8:>8}")

for election_type in ["primary", "general"]:
    for scenario in ["LOW", "EXPECTED", "HIGH"]:
        subset = scenarios_df[
            (scenarios_df["election_type"] == election_type) &
            (scenarios_df["scenario"] == scenario)
        ]
        total_reg = subset["registered_voters"].sum()
        total_bal = subset["estimated_ballots"].sum()
        rate = total_bal / total_reg if total_reg > 0 else 0
        label = f"{'Jun 2026' if election_type == 'primary' else 'Nov 2026'} {election_type.title()}"
        print(f"  {label:<20} {scenario:<10} {total_reg:>12,} {total_bal:>14,} {rate:>8.1%}")

# Also show CD11-only numbers
print(f"\n  CD11 ONLY (excl. Sup D11):")
print(f"  {'Election':<20} {'Scenario':<10} {'Registered':>12} {'Est. Ballots':>14} {'Turnout':>8}")
print(f"  {'-'*20:<20} {'-'*10:<10} {'-'*12:>12} {'-'*14:>14} {'-'*8:>8}")

for election_type in ["primary", "general"]:
    for scenario in ["LOW", "EXPECTED", "HIGH"]:
        subset = scenarios_df[
            (scenarios_df["election_type"] == election_type) &
            (scenarios_df["scenario"] == scenario) &
            (scenarios_df["in_cd11"] == True)
        ]
        total_reg = subset["registered_voters"].sum()
        total_bal = subset["estimated_ballots"].sum()
        rate = total_bal / total_reg if total_reg > 0 else 0
        label = f"{'Jun 2026' if election_type == 'primary' else 'Nov 2026'} {election_type.title()}"
        print(f"  {label:<20} {scenario:<10} {total_reg:>12,} {total_bal:>14,} {rate:>8.1%}")

print("\n" + "=" * 70)
print("STEP 4 COMPLETE")
print("=" * 70)
