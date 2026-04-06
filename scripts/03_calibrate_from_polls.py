#!/usr/bin/env python3
"""
Step 3: Calibrate Using Poll Crosstabs
========================================
Builds calibration multipliers by comparing the demographic composition of
the likely voter samples (from the Feb 2026 and Sept 2025 polls) to the
registered voter file's demographic composition.

The logic: If 65+ voters make up 28% of the likely voter sample but only 22%
of the registered voter file, their relative turnout propensity is 28/22 = 1.27.
This multiplier is applied in Step 4 to adjust historical base rates.

Both polls were already screened for likely voters, so we use sample composition
ratios rather than traditional "will you vote" likelihood rates.

Input:  data/processed/precinct_universe.csv
        data/processed/demographic_turnout_rates.csv
        Feb 2026 poll crosstabs (Excel)
        Sept 2025 poll slides (PDF — approximate extraction)

Output: data/processed/calibration_weights.csv

To install required packages:
    pip install pandas numpy openpyxl

To run:
    python scripts/03_calibrate_from_polls.py
"""

# ── Required packages ──────────────────────────────────────────────────────────
import pandas as pd
import numpy as np
import os

# ── FILE PATHS ─────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PRECINCT_UNIVERSE = os.path.join(BASE_DIR, "data", "processed", "precinct_universe.csv")
DEMO_RATES = os.path.join(BASE_DIR, "data", "processed", "demographic_turnout_rates.csv")
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "processed")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "calibration_weights.csv")

# February 2026 poll crosstabs (Excel)
FEB_2026_POLL = "/Users/joshraznick/Desktop/Wiener/Polling/Crosstabs March 2026.xlsx"

# ── STEP 3A: Load voter file demographics (the "denominator") ────────────────
print("=" * 70)
print("STEP 3: CALIBRATE USING POLL CROSSTABS")
print("=" * 70)

print(f"\nLoading precinct universe: {PRECINCT_UNIVERSE}")
universe = pd.read_csv(PRECINCT_UNIVERSE, dtype={"PrecinctName": str})

# Calculate CD11 voter file demographic shares (exclude Sup D11)
cd11 = universe[universe["in_cd11"] == True]
total_cd11_voters = cd11["total_registered"].sum()
print(f"  CD11 registered voters: {int(total_cd11_voters):,}")

# Calculate voter file shares for each demographic group
# These represent the "registered voter file composition" — our denominator
voter_file_shares = {}

# Age groups
for col in ["age_18-29", "age_30-44", "age_45-64", "age_65+"]:
    group_name = col.replace("age_", "")
    voter_file_shares[("age", group_name)] = cd11[col].sum() / total_cd11_voters

# Race groups
for col in ["race_Asian", "race_Black", "race_Latino/Hispanic", "race_White", "race_Other/Unknown"]:
    group_name = col.replace("race_", "")
    voter_file_shares[("race", group_name)] = cd11[col].sum() / total_cd11_voters

# Party groups
for col in ["party_Democrat", "party_NPP", "party_Other", "party_Republican"]:
    group_name = col.replace("party_", "")
    voter_file_shares[("party", group_name)] = cd11[col].sum() / total_cd11_voters

print("\n  Voter File Demographic Shares (CD11):")
for (dim, grp), share in sorted(voter_file_shares.items()):
    print(f"    {dim:6s} | {grp:20s}: {share:.1%}")

# ── STEP 3B: Extract February 2026 poll demographic composition ──────────────
print("\n── FEBRUARY 2026 POLL COMPOSITION ──")
print(f"  Source: {FEB_2026_POLL}")

# Read the Crosstabs sheet. The demographic breakdown rows are at the bottom
# of the sheet (rows ~651–790). We parse the specific rows identified during
# our initial investigation.
df_xt = pd.read_excel(FEB_2026_POLL, sheet_name="Crosstabs", header=None)

# The Feb 2026 poll sample composition (from row analysis):
# Row 654-658: Age (Self-ID and Sample) with n and %
# Row 740-758: Ethnicity (Self-ID, MR)
# Row 759-761: Party Registration (Sample)

# We extract the sample percentages directly from the crosstab.
# Column index 3 contains the overall sample percentage (%).

feb_2026_shares = {}

# --- Age ---
# Row 654: 18-29 = 9%, Row 655: 30-39 = 21%, Row 656: 40-49 = 17%,
# Row 657: 50-64 = 25%, Row 658: 65+ = 28%
# Map to our age buckets: 18-29, 30-44 (combine 30-39 + 40-49), 45-64, 65+
age_data = {
    "18-29": float(df_xt.iloc[654, 3]),   # 0.09
    "30-44": float(df_xt.iloc[655, 3]) + float(df_xt.iloc[656, 3]),  # 0.21 + 0.17 = 0.38
    "45-64": float(df_xt.iloc[657, 3]),   # 0.25
    "65+": float(df_xt.iloc[658, 3]),     # 0.28
}
# Note: The poll uses 30-39 and 40-49; we combine to match our 30-44 bucket.
# This is an approximation since our bucket is 30-44 and theirs is 30-39 + 40-49.
for grp, share in age_data.items():
    feb_2026_shares[("age", grp)] = share

print("  Age composition:")
for grp, share in age_data.items():
    print(f"    {grp:20s}: {share:.0%}")

# --- Race/Ethnicity ---
# Row 752-757 has the collapsed ethnicity breakdown matching our categories:
# Row 752: Hispanic or Latino, Row 753: White, Row 754: Black/African American
# Row 755: Asian or Pacific Islander, Row 756: Something else, Row 757: Prefer not to respond
race_data = {
    "Latino/Hispanic": float(df_xt.iloc[752, 3]),   # 0.068
    "White": float(df_xt.iloc[753, 3]),              # 0.568
    "Black": float(df_xt.iloc[754, 3]),              # 0.066
    "Asian": float(df_xt.iloc[755, 3]),              # 0.226
    "Other/Unknown": float(df_xt.iloc[756, 3]) + float(df_xt.iloc[757, 3]),  # something else + prefer not
}
for grp, share in race_data.items():
    feb_2026_shares[("race", grp)] = share

print("  Race composition:")
for grp, share in race_data.items():
    print(f"    {grp:20s}: {share:.1%}")

# --- Party ---
# Row 759: Democrat = 70%, Row 760: Republican = 7%, Row 761: NPP/Other = 23%
party_data = {
    "Democrat": float(df_xt.iloc[759, 3]),     # 0.70
    "Republican": float(df_xt.iloc[760, 3]),   # 0.07
    "NPP": float(df_xt.iloc[761, 3]),          # 0.23 (includes all non-D, non-R)
    "Other": 0.0,  # Lumped into NPP in this poll
}
# The poll combines NPP + Other into one "NPP/Other" bucket at 23%.
# Our voter file separates NPP (24.7%) from Other (4.4%).
# We'll split the poll's 23% proportionally to the voter file ratio.
vf_npp = voter_file_shares[("party", "NPP")]
vf_other = voter_file_shares[("party", "Other")]
npp_other_total = vf_npp + vf_other
if npp_other_total > 0:
    party_data["NPP"] = float(df_xt.iloc[761, 3]) * (vf_npp / npp_other_total)
    party_data["Other"] = float(df_xt.iloc[761, 3]) * (vf_other / npp_other_total)

for grp, share in party_data.items():
    feb_2026_shares[("party", grp)] = share

print("  Party composition:")
for grp, share in party_data.items():
    print(f"    {grp:20s}: {share:.1%}")

# ── STEP 3C: Extract September 2025 poll demographic composition ─────────────
print("\n── SEPTEMBER 2025 POLL COMPOSITION ──")
print("  Source: PDF slide deck (approximate extraction from subgroup labels)")

# From the September 2025 slides, the demographic subgroup labels show:
# Democrat (71%), Rep/NPP (29%)
# White (68%), Asian or Pacific Islander (14%), Hispanic or Latino (12%)
# Men: 18-49 (26%), Men: 50+ (25%), Women: 18-49 (21%), Women: 50+ (28%)
#   => 18-49: 47%, 50+: 53%
# Black percentage not directly shown in slides — approximate from remainder

sept_2025_shares = {}

# --- Age ---
# The Sept 2025 poll uses 18-49 / 50+ split, not our four buckets.
# We'll distribute the 18-49 and 50+ shares proportionally using the voter
# file's sub-distribution within each age range.
sept_1849 = 0.47  # 18-49 combined
sept_50plus = 0.53  # 50+ combined

# Voter file ratios within 18-49: 18-29 and 30-44
vf_1829 = voter_file_shares[("age", "18-29")]
vf_3044 = voter_file_shares[("age", "30-44")]
vf_4564 = voter_file_shares[("age", "45-64")]
vf_65plus = voter_file_shares[("age", "65+")]

ratio_1829_in_young = vf_1829 / (vf_1829 + vf_3044) if (vf_1829 + vf_3044) > 0 else 0.5
ratio_3044_in_young = vf_3044 / (vf_1829 + vf_3044) if (vf_1829 + vf_3044) > 0 else 0.5
ratio_4564_in_old = vf_4564 / (vf_4564 + vf_65plus) if (vf_4564 + vf_65plus) > 0 else 0.5
ratio_65_in_old = vf_65plus / (vf_4564 + vf_65plus) if (vf_4564 + vf_65plus) > 0 else 0.5

sept_2025_shares[("age", "18-29")] = sept_1849 * ratio_1829_in_young
sept_2025_shares[("age", "30-44")] = sept_1849 * ratio_3044_in_young
sept_2025_shares[("age", "45-64")] = sept_50plus * ratio_4564_in_old
sept_2025_shares[("age", "65+")] = sept_50plus * ratio_65_in_old

print("  Age composition (estimated from 18-49/50+ split):")
for grp in ["18-29", "30-44", "45-64", "65+"]:
    print(f"    {grp:20s}: {sept_2025_shares[('age', grp)]:.1%}")

# --- Race/Ethnicity ---
# From slides: White (68%), API (14%), Hispanic/Latino (12%)
# Black not shown directly; estimate as remainder after others
sept_white = 0.68
sept_asian = 0.14
sept_latino = 0.12
# The remaining ~ 6% is Black + Other/Unknown
# Distribute proportionally from voter file
vf_black = voter_file_shares[("race", "Black")]
vf_other_unk = voter_file_shares[("race", "Other/Unknown")]
remaining = 1.0 - sept_white - sept_asian - sept_latino
black_ratio = vf_black / (vf_black + vf_other_unk) if (vf_black + vf_other_unk) > 0 else 0.5

sept_2025_shares[("race", "White")] = sept_white
sept_2025_shares[("race", "Asian")] = sept_asian
sept_2025_shares[("race", "Latino/Hispanic")] = sept_latino
sept_2025_shares[("race", "Black")] = remaining * black_ratio
sept_2025_shares[("race", "Other/Unknown")] = remaining * (1 - black_ratio)

print("  Race composition:")
for grp in ["White", "Asian", "Latino/Hispanic", "Black", "Other/Unknown"]:
    print(f"    {grp:20s}: {sept_2025_shares[('race', grp)]:.1%}")

# --- Party ---
# From slides: Democrat (71%), Rep/NPP (29%)
# Split the non-Democratic share using voter file ratios
sept_dem = 0.71
sept_non_dem = 0.29

vf_rep = voter_file_shares[("party", "Republican")]
vf_npp = voter_file_shares[("party", "NPP")]
vf_other_p = voter_file_shares[("party", "Other")]
non_dem_total = vf_rep + vf_npp + vf_other_p

sept_2025_shares[("party", "Democrat")] = sept_dem
sept_2025_shares[("party", "Republican")] = sept_non_dem * (vf_rep / non_dem_total) if non_dem_total > 0 else 0
sept_2025_shares[("party", "NPP")] = sept_non_dem * (vf_npp / non_dem_total) if non_dem_total > 0 else 0
sept_2025_shares[("party", "Other")] = sept_non_dem * (vf_other_p / non_dem_total) if non_dem_total > 0 else 0

print("  Party composition:")
for grp in ["Democrat", "Republican", "NPP", "Other"]:
    print(f"    {grp:20s}: {sept_2025_shares[('party', grp)]:.1%}")

# ── STEP 3D: Weighted average of both polls ───────────────────────────────────
print("\n── WEIGHTED AVERAGE (60% Feb 2026, 40% Sept 2025) ──")

# Weight Feb 2026 at 60% and Sept 2025 at 40% due to recency
FEB_WEIGHT = 0.60
SEPT_WEIGHT = 0.40

blended_shares = {}
for key in feb_2026_shares:
    feb_val = feb_2026_shares.get(key, 0)
    sept_val = sept_2025_shares.get(key, 0)
    blended = (feb_val * FEB_WEIGHT) + (sept_val * SEPT_WEIGHT)
    blended_shares[key] = blended

print("  Blended Likely Voter Shares:")
for (dim, grp), share in sorted(blended_shares.items()):
    vf_share = voter_file_shares.get((dim, grp), 0)
    print(f"    {dim:6s} | {grp:20s}: Poll={share:.1%}  VoterFile={vf_share:.1%}")

# ── STEP 3E: Calculate calibration multipliers ────────────────────────────────
print("\n── CALIBRATION MULTIPLIERS ──")
print("  Multiplier = poll likely voter share / voter file share")
print("  Values > 1.0 mean the group turns out at HIGHER rates in 2026 polls")
print("  Values < 1.0 mean the group turns out at LOWER rates in 2026 polls\n")

calibration_rows = []

for (dim, grp), poll_share in blended_shares.items():
    vf_share = voter_file_shares.get((dim, grp), 0)

    if vf_share > 0:
        multiplier = poll_share / vf_share
    else:
        multiplier = 1.0  # if voter file has 0, default to no adjustment

    # Sanity check: flag multipliers below 0.5 or above 2.0
    flag = ""
    if multiplier < 0.5:
        flag = " *** SUSPECT: < 0.5 ***"
    elif multiplier > 2.0:
        flag = " *** SUSPECT: > 2.0 ***"

    calibration_rows.append({
        "dimension": dim,
        "group": grp,
        "poll_likely_voter_share": round(poll_share, 4),
        "voter_file_share": round(vf_share, 4),
        "calibration_multiplier": round(multiplier, 4),
        "feb_2026_share": round(feb_2026_shares.get((dim, grp), 0), 4),
        "sept_2025_share": round(sept_2025_shares.get((dim, grp), 0), 4),
    })

    print(f"  {dim:6s} | {grp:20s}: {multiplier:.3f}  (poll {poll_share:.1%} / vf {vf_share:.1%}){flag}")

calibration_df = pd.DataFrame(calibration_rows)

# ── STEP 3F: Sanity checks ───────────────────────────────────────────────────
print("\n── SANITY CHECKS ──")

suspect = calibration_df[
    (calibration_df["calibration_multiplier"] < 0.5) |
    (calibration_df["calibration_multiplier"] > 2.0)
]

if len(suspect) > 0:
    print(f"  WARNING: {len(suspect)} multipliers are outside the 0.5–2.0 range:")
    for _, row in suspect.iterrows():
        print(f"    {row['dimension']} | {row['group']}: {row['calibration_multiplier']:.3f}")
else:
    print("  All multipliers are within the 0.5–2.0 acceptable range.")

# Check that shares within each dimension sum to ~1.0
for dim in ["age", "race", "party"]:
    dim_sum = calibration_df[calibration_df["dimension"] == dim]["poll_likely_voter_share"].sum()
    print(f"  {dim} poll shares sum: {dim_sum:.2f} (should be ~1.00)")

# ── STEP 3G: Save output ─────────────────────────────────────────────────────
print("\n── SAVING OUTPUT ──")

os.makedirs(OUTPUT_DIR, exist_ok=True)
calibration_df.to_csv(OUTPUT_FILE, index=False)
print(f"  Saved calibration weights to: {OUTPUT_FILE}")

print("\n── SUMMARY ──")
print(f"  Total calibration multipliers: {len(calibration_df)}")
print(f"  Dimensions covered: age, race, party")
print(f"  Weighting: {FEB_WEIGHT:.0%} February 2026, {SEPT_WEIGHT:.0%} September 2025")

# Print a clean summary table
print("\n  Final Calibration Multipliers:")
print(f"  {'Dimension':<8} {'Group':<20} {'Multiplier':>10}")
print(f"  {'-'*8:<8} {'-'*20:<20} {'-'*10:>10}")
for _, row in calibration_df.iterrows():
    m = row["calibration_multiplier"]
    arrow = "^" if m > 1.05 else ("v" if m < 0.95 else "=")
    print(f"  {row['dimension']:<8} {row['group']:<20} {m:>10.3f} {arrow}")

print("\n" + "=" * 70)
print("STEP 3 COMPLETE")
print("=" * 70)
