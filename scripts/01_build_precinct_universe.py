#!/usr/bin/env python3
"""
Step 1: Build the Precinct Universe
====================================
Reads the SF voter file (VAN export) and produces a precinct-level demographic
summary: counts of registered voters broken down by age group, race/ethnicity,
and party registration.

Output: data/processed/precinct_universe.csv

To install required packages:
    pip install pandas numpy

To run:
    python scripts/01_build_precinct_universe.py
"""

# ── Required packages ──────────────────────────────────────────────────────────
import pandas as pd
import numpy as np
import os
import sys

# ── FILE PATHS — change these if your files are in a different location ────────
# The voter file is a tab-delimited UTF-16 text file exported from VAN.
# Despite the .xls extension, it is NOT a true Excel file.
VOTER_FILE = "/Users/joshraznick/Desktop/Claude/CD 11 Full File.xls"

# Where to save the output
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "processed")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "precinct_universe.csv")

# ── STEP 1A: Load the voter file ──────────────────────────────────────────────
print("=" * 70)
print("STEP 1: BUILD PRECINCT UNIVERSE")
print("=" * 70)
print(f"\nReading voter file: {VOTER_FILE}")

# Only load the columns we need — this saves memory on large files
COLUMNS_TO_LOAD = [
    "Voter File VANID",   # unique voter ID
    "PrecinctName",       # precinct code (4-digit numeric)
    "CountySupervisorName",  # SF Supervisor District (1–11) — NOT the "SD" column
    "Age",                # numeric age
    "RaceName",           # race/ethnicity category
    "Party",              # party registration (D, R, U, G, L, P, O)
]

# Read the file. It uses UTF-16 encoding and tab separators.
df = pd.read_csv(
    VOTER_FILE,
    sep="\t",
    encoding="utf-16",
    usecols=COLUMNS_TO_LOAD,
    low_memory=False,
    dtype={"PrecinctName": str},  # keep precinct as string to preserve leading zeros
)

print(f"Loaded {len(df):,} voters")

# ── STEP 1B: Data quality report ──────────────────────────────────────────────
print("\n── DATA QUALITY REPORT ──")

# Count nulls in every key field
null_counts = df.isnull().sum()
print("\nNull/missing values per field:")
for col in COLUMNS_TO_LOAD:
    n = null_counts[col]
    pct = n / len(df) * 100
    flag = " *** FLAG ***" if pct > 1 else ""
    print(f"  {col:30s}: {n:>7,} ({pct:.2f}%){flag}")

# Flag voters with null precinct codes
null_precinct = df["PrecinctName"].isnull().sum()
if null_precinct > 0:
    print(f"\n  WARNING: {null_precinct:,} voters have null precinct codes — these will be excluded")
    df = df.dropna(subset=["PrecinctName"])

# Clean up precinct names — strip whitespace, remove trailing dots/decimals
df["PrecinctName"] = df["PrecinctName"].astype(str).str.strip()

# Check for race field completeness (brief says flag if >10% unknown)
race_unknown = df["RaceName"].isin(["Uncoded", ""]).sum() + df["RaceName"].isnull().sum()
race_unknown_pct = race_unknown / len(df) * 100
if race_unknown_pct > 10:
    print(f"\n  *** PROMINENT FLAG: {race_unknown_pct:.1f}% of voters have unknown/Uncoded race ***")
else:
    print(f"\n  Race unknown/Uncoded: {race_unknown:,} ({race_unknown_pct:.1f}%) — within acceptable range")

# ── STEP 1C: Create demographic categories ───────────────────────────────────
print("\n── CREATING DEMOGRAPHIC CATEGORIES ──")

# --- Age groups ---
# Convert Age to numeric; some values may be missing or non-numeric
df["Age"] = pd.to_numeric(df["Age"], errors="coerce")

# Assign age groups
def assign_age_group(age):
    """Puts each voter into one of four age buckets."""
    if pd.isna(age):
        return "Unknown"
    if age < 18:
        return "Under 18"  # shouldn't exist in a voter file, but flag it
    if age <= 29:
        return "18-29"
    if age <= 44:
        return "30-44"
    if age <= 64:
        return "45-64"
    return "65+"

df["age_group"] = df["Age"].apply(assign_age_group)

# Report age group distribution
print("\nAge group distribution:")
age_dist = df["age_group"].value_counts().sort_index()
for group, count in age_dist.items():
    print(f"  {group:15s}: {count:>8,} ({count/len(df)*100:.1f}%)")

# Flag any "Under 18" voters (shouldn't exist)
under_18 = (df["age_group"] == "Under 18").sum()
if under_18 > 0:
    print(f"\n  WARNING: {under_18} voters are under 18 — excluding from universe")
    df = df[df["age_group"] != "Under 18"]

# --- Race/Ethnicity ---
# Map the voter file race values to the categories used in the model
RACE_MAP = {
    "White": "White",
    "Asian or Pacific Islander": "Asian",
    "Hispanic or Latino": "Latino/Hispanic",
    "Black": "Black",
    "Uncoded": "Other/Unknown",
    "Native American": "Other/Unknown",
}

df["race_group"] = df["RaceName"].map(RACE_MAP).fillna("Other/Unknown")

print("\nRace/Ethnicity distribution:")
race_dist = df["race_group"].value_counts().sort_index()
for group, count in race_dist.items():
    print(f"  {group:15s}: {count:>8,} ({count/len(df)*100:.1f}%)")

# --- Party Registration ---
# Map party codes to readable labels
PARTY_MAP = {
    "D": "Democrat",
    "R": "Republican",
    "U": "NPP",          # No Party Preference / Decline to State
    "G": "Other",         # Green
    "L": "Other",         # Libertarian
    "P": "Other",         # Peace & Freedom
    "O": "Other",         # Other
}

df["party_group"] = df["Party"].map(PARTY_MAP).fillna("Other")

print("\nParty registration distribution:")
party_dist = df["party_group"].value_counts().sort_index()
for group, count in party_dist.items():
    print(f"  {group:15s}: {count:>8,} ({count/len(df)*100:.1f}%)")

# ── STEP 1D: Tag Supervisor District and CD11 flag ────────────────────────────
print("\n── SUPERVISOR DISTRICT AND CD11 TAG ──")

# "CountySupervisorName" holds the SF Board of Supervisors district number (1–11).
# CD11 (the congressional district) includes all of SF EXCEPT Supervisor District 11
# (the Excelsior/Outer Mission area).
df["sup_district"] = pd.to_numeric(df["CountySupervisorName"], errors="coerce").astype("Int64")

# in_cd11 is True for everyone NOT in Supervisor District 11
df["in_cd11"] = df["sup_district"] != 11

print("Supervisor District distribution:")
sup_dist = df["sup_district"].value_counts().sort_index()
for dist, count in sup_dist.items():
    cd11_tag = "" if dist != 11 else " (EXCLUDED from CD11)"
    print(f"  District {dist:>2}: {count:>8,} voters{cd11_tag}")

cd11_total = df["in_cd11"].sum()
print(f"\nCD11 total (excl. Sup D11): {cd11_total:,}")
print(f"Sup D11 voters:             {(~df['in_cd11']).sum():,}")

# ── STEP 1E: Build the precinct-level universe ────────────────────────────────
print("\n── BUILDING PRECINCT UNIVERSE ──")

# For each precinct, count total registered voters and break down by demographics.
# We'll create one row per precinct with columns for each demographic cell.

# First, get the precinct-level totals and metadata
precinct_meta = df.groupby("PrecinctName").agg(
    total_registered=("Voter File VANID", "count"),
    sup_district=("sup_district", "first"),       # each precinct belongs to one district
    in_cd11=("in_cd11", "first"),
).reset_index()

# --- Age group counts per precinct ---
age_pivot = df.groupby(["PrecinctName", "age_group"]).size().unstack(fill_value=0)
# Rename columns with "age_" prefix
age_pivot.columns = [f"age_{col}" for col in age_pivot.columns]
age_pivot = age_pivot.reset_index()

# --- Race group counts per precinct ---
race_pivot = df.groupby(["PrecinctName", "race_group"]).size().unstack(fill_value=0)
race_pivot.columns = [f"race_{col}" for col in race_pivot.columns]
race_pivot = race_pivot.reset_index()

# --- Party group counts per precinct ---
party_pivot = df.groupby(["PrecinctName", "party_group"]).size().unstack(fill_value=0)
party_pivot.columns = [f"party_{col}" for col in party_pivot.columns]
party_pivot = party_pivot.reset_index()

# Merge everything together on PrecinctName
precinct_universe = precinct_meta.merge(age_pivot, on="PrecinctName", how="left")
precinct_universe = precinct_universe.merge(race_pivot, on="PrecinctName", how="left")
precinct_universe = precinct_universe.merge(party_pivot, on="PrecinctName", how="left")

# Fill any NaN demographic counts with 0 (happens when a group doesn't exist in a precinct)
numeric_cols = precinct_universe.select_dtypes(include=[np.number]).columns
precinct_universe[numeric_cols] = precinct_universe[numeric_cols].fillna(0)

print(f"Precinct universe built: {len(precinct_universe)} precincts")
print(f"Columns: {list(precinct_universe.columns)}")

# ── STEP 1F: Data quality flags ──────────────────────────────────────────────
print("\n── PRECINCT-LEVEL QUALITY FLAGS ──")

# Flag precincts with fewer than 50 total registered voters
small_precincts = precinct_universe[precinct_universe["total_registered"] < 50]
print(f"\nPrecincts with < 50 registered voters (too small for reliable estimates): {len(small_precincts)}")
if len(small_precincts) > 0:
    for _, row in small_precincts.iterrows():
        print(f"  Precinct {row['PrecinctName']}: {int(row['total_registered'])} voters (Sup D{int(row['sup_district'])})")

# Flag demographic cells with fewer than 25 voters in any precinct
# We'll check each demographic column
print("\nPrecincts with very small demographic cells (< 25 voters):")
demo_cols = [c for c in precinct_universe.columns if c.startswith(("age_", "race_", "party_"))]
small_cell_count = 0
for col in demo_cols:
    n_small = (precinct_universe[col] < 25).sum()
    if n_small > 0:
        small_cell_count += n_small
        # Only print if this is a meaningful category (not "Unknown" or "Other")
        if "Unknown" not in col and "Other" not in col:
            print(f"  {col}: {n_small} precincts have < 25 voters in this cell")

print(f"\n  Total small demographic cells across all precincts: {small_cell_count:,}")
print("  (These cells will be flagged as LOW CONFIDENCE in the dashboard)")

# ── STEP 1G: Save output ─────────────────────────────────────────────────────
print("\n── SAVING OUTPUT ──")

# Make sure the output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Save to CSV
precinct_universe.to_csv(OUTPUT_FILE, index=False)
print(f"Saved precinct universe to: {OUTPUT_FILE}")

# Print summary stats
print(f"\n── SUMMARY ──")
print(f"Total precincts:           {len(precinct_universe):,}")
print(f"Total registered voters:   {int(precinct_universe['total_registered'].sum()):,}")
print(f"CD11 precincts:            {precinct_universe['in_cd11'].sum():,}")
print(f"Sup D11 precincts:         {(~precinct_universe['in_cd11']).sum():,}")
print(f"CD11 registered voters:    {int(precinct_universe.loc[precinct_universe['in_cd11'], 'total_registered'].sum()):,}")
print(f"Sup D11 registered voters: {int(precinct_universe.loc[~precinct_universe['in_cd11'], 'total_registered'].sum()):,}")

# Print a quick demographic summary at the citywide level
print("\n── CITYWIDE DEMOGRAPHIC SUMMARY ──")
for prefix, label in [("age_", "Age"), ("race_", "Race"), ("party_", "Party")]:
    print(f"\n{label}:")
    cols = [c for c in precinct_universe.columns if c.startswith(prefix)]
    for col in sorted(cols):
        total = int(precinct_universe[col].sum())
        pct = total / precinct_universe["total_registered"].sum() * 100
        clean_name = col.replace(prefix, "")
        print(f"  {clean_name:20s}: {total:>8,} ({pct:.1f}%)")

print("\n" + "=" * 70)
print("STEP 1 COMPLETE")
print("=" * 70)
