"""
07_build_support_and_universes.py

Builds a synthetic support score (0-100) for every voter in the CD-11 voter file,
calibrates against real voter IDs from phone banking/canvassing, and assigns
targeting universe flags (Base / Persuasion / Opposition).

Scott Wiener for Congress (CA CD-11) — June 2026 Primary

v2: Rewritten to use EMC Research polling crosstabs as primary calibration source.
    VAN ID scores used as soft validation only (they don't discriminate well in
    all-Dem SF primaries). Opposition defined as Saikat supporters + MAGA.

Inputs:
    - FULL CD 11 with IDs + Scores.xls (451K voters, TargetSmart-enriched VAN export)
    - ALL SW IDs_4.6.xls (985 real voter IDs from phone banking, 1-5 scale)

Outputs:
    - cd11_voters_with_scores.csv (full voter file with support_score, universe flags)
    - calibration_report.csv (calibration results by ID bucket)
    - universe_summary.csv (universe sizes and demographics)

Scoring Model v2 (crosstab-calibrated):
    6 key factors, max raw = 100, directly used as support_score.
    Primary signal: Ideology (crosstab-mapped) + LGBTQ+ identity.
    Secondary signals: Race, Age, Education, Vote frequency.
    Thresholds tuned to produce ~38% Base (matching polling True Base).
"""

import pandas as pd
import numpy as np
import os
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# CONFIGURATION
# ============================================================

VOTER_FILE = '/Users/joshraznick/Downloads/FULL CD 11 with IDs + Scores.xls'
ID_FILE = '/Users/joshraznick/Desktop/Wiener/IDs/ALL SW IDs_4.6.xls'
OUTPUT_DIR = '/Users/joshraznick/Desktop/Claude/turnout_model/data/processed/'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Universe thresholds — tuned so Base ≈ 38% of electorate (matching polling True Base)
SUPPORT_BASE_THRESHOLD = 65       # >= this = Base (tuned for ~38% matching polling True Base)
SUPPORT_PERSUASION_LOW = 40       # >= this and < Base = Persuasion
TURNOUT_DROPOFF_THRESHOLD = 45    # Base voters below this turnout score = drop-off targets (0-100 scale)

# ============================================================
# STEP 1: LOAD DATA
# ============================================================

print("=" * 70)
print("STEP 1: LOADING DATA")
print("=" * 70)

print("Loading voter file...")
vf = pd.read_csv(VOTER_FILE, sep='\t', encoding='utf-16', low_memory=False)
print(f"  Loaded {len(vf):,} voters, {len(vf.columns)} columns")

print("Loading real voter IDs...")
ids = pd.read_csv(ID_FILE, sep='\t', encoding='utf-16')
ids['Voter_ID_Score'] = ids['Voter_ID_Score'].str.strip()
print(f"  Loaded {len(ids):,} real voter IDs")
print(f"  ID score distribution:")
for score in sorted(ids['Voter_ID_Score'].unique()):
    n = (ids['Voter_ID_Score'] == score).sum()
    print(f"    {score}: {n} ({n/len(ids)*100:.1f}%)")

# ============================================================
# STEP 2: DATA CLEANING & EXCLUSIONS
# ============================================================

print("\n" + "=" * 70)
print("STEP 2: DATA CLEANING & EXCLUSIONS")
print("=" * 70)

# Exclude Supervisor District 11 (not in CD-11)
before = len(vf)
vf = vf[vf['CountySupervisorName'] != 11].copy()
excluded = before - len(vf)
print(f"  Excluded {excluded:,} voters in Sup District 11")
print(f"  Working universe: {len(vf):,} voters")

# Data quality checks
print("\n  Data quality checks:")
for col in ['Age', 'Sex', 'RaceName', 'Party', 'PrecinctName', 'CountySupervisorName']:
    nulls = vf[col].isna().sum()
    pct = nulls / len(vf) * 100
    flag = " WARNING" if pct > 1 else ""
    print(f"    {col}: {nulls:,} nulls ({pct:.1f}%){flag}")

print("\n  TargetSmart score coverage:")
for col in ['Ideo', 'HomeOwner', 'CollGrd', 'MarEqu', 'Don2HCOrg',
            'NonPresPriTO', 'TSMTrumpSup', 'TSMHarrisSupp']:
    nulls = vf[col].isna().sum()
    pct = nulls / len(vf) * 100
    print(f"    {col}: {len(vf) - nulls:,} available ({100-pct:.1f}%), {nulls:,} missing ({pct:.1f}%)")

# ============================================================
# STEP 3: COMPUTE VOTE FREQUENCY
# ============================================================

print("\n" + "=" * 70)
print("STEP 3: COMPUTING VOTE FREQUENCY")
print("=" * 70)

# Count votes across 6 most recent major elections
vote_cols = ['General24', 'General22', 'General20', 'General18', 'General16', 'Primary24']

print(f"  Counting participation across {len(vote_cols)} elections:")
for col in vote_cols:
    voted = vf[col].isin(['A', 'P']).sum()
    print(f"    {col}: {voted:,} voted ({voted/len(vf)*100:.1f}%)")

vote_matrix = pd.DataFrame()
for col in vote_cols:
    vote_matrix[col] = vf[col].isin(['A', 'P']).astype(int)
vf['vote_count_6'] = vote_matrix.sum(axis=1)

# Vote frequency score on 0-100 scale (vote_count_6 / 6 * 100)
vf['vote_frequency_score'] = (vf['vote_count_6'] / 6 * 100).round(1)

# Perfect voter flag (6/6)
vf['is_perfect_voter'] = (vf['vote_count_6'] == 6)
print(f"\n  Perfect voters (6/6): {vf['is_perfect_voter'].sum():,} ({vf['is_perfect_voter'].mean()*100:.1f}%)")

print(f"\n  Vote frequency distribution:")
for count in range(7):
    n = (vf['vote_count_6'] == count).sum()
    print(f"    {count}/6 elections: {n:,} voters ({n/len(vf)*100:.1f}%)")

# ============================================================
# STEP 4: BUILD SUPPORT SCORE v2 (CROSSTAB-CALIBRATED)
# ============================================================

print("\n" + "=" * 70)
print("STEP 4: BUILDING SUPPORT SCORE v2 (CROSSTAB-CALIBRATED)")
print("=" * 70)

# Scoring philosophy:
# - Primary drivers: Ideology (biggest spread in crosstabs: 28pts) and LGBTQ+ (8pt spread)
# - Secondary signals: Race, Age, Education, Vote frequency (all <12pt spread in crosstabs)
# - Party is DE-WEIGHTED because SF is 64% Dem — it doesn't discriminate in a Dem primary
# - Geography handled via Supervisor District (13pt spread in crosstabs)
# - Opposition explicitly identified via TS scores (Trump support, very progressive)
#
# Crosstab reference (EMC Research Feb 2026, n=800, Q10 Initial Ballot w/ leaners):
#   Ideology:   Liberal 64.2% | Moderate 41.7% | Progressive 36.3% | Conservative 22.4%
#   LGBTQ+:     LGBTQ+ 50.9% | Non-LGBTQ+ 42.8%
#   Race:       Black 58.5% | API 49.9% | White 46.7% | Hispanic 29.2%
#   Age:        18-29: 54.7% | 30-39: 44.7% | 40-49: 47.3% | 50-64: 43.9% | 65+: 41.6%
#   Education:  College 46.7% | Non-college 35.9%
#   Frequency:  New/Infreq 46.9% | Frequent 45.2% | Perfect 44.2%
#   Geography:  BoS 2,3,6: 51.2% | BoS 7,8: 47.8% | BoS 5,9: 41.2% | BoS 1,4: 38.5%
#
# User direction: 50+ = slight Scott, under 30 = slight Saikat
#   (Strategic view of where race is heading, not current snapshot)

# --- FACTOR 1: Ideology (max +30) ---
# THIS IS THE PRIMARY DRIVER — 28pt spread between Liberal and Progressive
# TS Ideo score: higher = more progressive (national scale)
# In SF: Liberal (TS ~70-84) = Scott's base; Progressive (TS 85+) = Saikat's zone
# Moderate (TS 55-69) = lean Scott; Conservative (TS <55) = opposition
#
# Mapping TS Ideo → crosstab ideology categories:
#   TS 70-84  → "Liberal" (crosstab: 64.2% Scott) → max points
#   TS 55-69  → "Moderate" (crosstab: 41.7% Scott) → medium points
#   TS 85-91  → "Progressive" (crosstab: 36.3% Scott) → low points
#   TS 92+    → "Very Progressive" (Saikat core) → minimal points
#   TS <55    → "Conservative" (crosstab: 22.4% Scott) → minimal points
#   Missing   → neutral default

ideo_conditions = [
    (vf['Ideo'] >= 70) & (vf['Ideo'] < 85),    # Liberal sweet spot
    (vf['Ideo'] >= 55) & (vf['Ideo'] < 70),     # Moderate-liberal
    (vf['Ideo'] >= 85) & (vf['Ideo'] < 92),     # Progressive (not extreme)
    (vf['Ideo'] >= 92),                           # Very progressive → Saikat zone
    (vf['Ideo'] >= 40) & (vf['Ideo'] < 55),      # Moderate-conservative
    (vf['Ideo'] < 40),                            # Conservative → opposition
    vf['Ideo'].isna(),                            # Missing
]
ideo_values = [30, 18, 8, 3, 5, 0, 12]
vf['pts_ideology'] = np.select(ideo_conditions, ideo_values, default=12)
print(f"  Factor 1 - Ideology (max 30): mean={vf['pts_ideology'].mean():.1f}")

# Show ideology band distribution
for label, cond in [('Liberal (70-84)', (vf['Ideo'] >= 70) & (vf['Ideo'] < 85)),
                     ('Moderate (55-69)', (vf['Ideo'] >= 55) & (vf['Ideo'] < 70)),
                     ('Progressive (85-91)', (vf['Ideo'] >= 85) & (vf['Ideo'] < 92)),
                     ('Very Prog (92+)', vf['Ideo'] >= 92),
                     ('Mod-Con (40-54)', (vf['Ideo'] >= 40) & (vf['Ideo'] < 55)),
                     ('Conservative (<40)', vf['Ideo'] < 40),
                     ('Missing', vf['Ideo'].isna())]:
    n = cond.sum()
    print(f"    {label:25s}: {n:>8,} ({n/len(vf)*100:.1f}%)")

# --- FACTOR 2: LGBTQ+ Proxy (max +20) ---
# Polling: LGBTQ+ 50.9% vs Non-LGBTQ+ 42.8% (8pt spread)
# User said this is a "good indicator" — elevated from v1's max 6 to max 20
# Using Marriage Equality support (MarEqu) + HC Org donation (Don2HCOrg) as proxies
# For SF specifically: high MarEqu is baseline, so we need VERY high or donation to signal

lgbtq_conditions = [
    vf['Don2HCOrg'] == 1,                                     # Donated to LGBTQ+ org — strong signal
    (vf['Don2HCOrg'] != 1) & (vf['MarEqu'] > 95),            # Very top of MarEqu — likely LGBTQ+
    (vf['Don2HCOrg'] != 1) & (vf['MarEqu'] > 90) & (vf['MarEqu'] <= 95),  # High but not extreme
    (vf['Don2HCOrg'] != 1) & (vf['MarEqu'] > 85) & (vf['MarEqu'] <= 90),  # Above average
    (vf['MarEqu'] <= 85) | vf['MarEqu'].isna(),               # Below SF average or missing
]
lgbtq_values = [20, 20, 12, 5, 0]
vf['pts_lgbtq'] = np.select(lgbtq_conditions, lgbtq_values, default=0)
print(f"  Factor 2 - LGBTQ+ Proxy (max 20): mean={vf['pts_lgbtq'].mean():.1f}")

# --- FACTOR 3: Geography / Supervisor District (max +15) ---
# Polling: BoS 2,3,6: 51.2%; BoS 7,8: 47.8%; BoS 5,9: 41.2%; BoS 10: 41.5%; BoS 1,4: 38.5%
# 13pt spread — meaningful signal, especially District 8 (Castro — Wiener's home base)
geo_map = {2: 15, 3: 15, 6: 15, 7: 12, 8: 12, 5: 5, 9: 5, 10: 5, 1: 0, 4: 0}
vf['pts_geography'] = vf['CountySupervisorName'].map(geo_map).fillna(5)
print(f"  Factor 3 - Geography (max 15): mean={vf['pts_geography'].mean():.1f}")

# --- FACTOR 4: Race/Ethnicity (max +10) ---
# Polling: API 49.9%, White 46.7%, Black 58.5% (small n=53), Hispanic 29.2%
# User: White and Asian = slight Scott indicator
# Black at 58.5% but n=53, treat cautiously
race_map = {
    'Asian or Pacific Islander': 10,
    'White': 8,
    'Black': 6,           # High in polling but very small n
    'Native American': 3,
    'Uncoded': 3,
    'Hispanic or Latino': 0,
}
vf['pts_race'] = vf['RaceName'].map(race_map).fillna(3)
print(f"  Factor 4 - Race (max 10): mean={vf['pts_race'].mean():.1f}")

# --- FACTOR 5: Age (max +8) ---
# User direction: 50+ = slight Scott indicator, under 30 = slight Saikat indicator
# This is a STRATEGIC view of where the race is heading, not current snapshot
# The polling shows young voters like Scott NOW, but user believes Saikat will
# gain ground with younger voters as campaign progresses
age_conditions = [
    vf['Age'] >= 65,                             # Senior — slight Scott
    (vf['Age'] >= 50) & (vf['Age'] < 65),        # Mature — slight Scott
    (vf['Age'] >= 40) & (vf['Age'] < 50),        # Middle-aged — neutral
    (vf['Age'] >= 30) & (vf['Age'] < 40),        # Younger adult — slight Saikat
    vf['Age'] < 30,                               # Young — slight Saikat
    vf['Age'].isna(),                             # Missing — neutral
]
age_values = [8, 6, 4, 2, 0, 3]
vf['pts_age'] = np.select(age_conditions, age_values, default=3)
print(f"  Factor 5 - Age (max 8): mean={vf['pts_age'].mean():.1f}")

# --- FACTOR 6: Education (max +7) ---
# Polling: College 46.7% vs Non-college 35.9% (11pt spread — meaningful)
edu_conditions = [
    vf['CollGrd'] > 65,                                        # Likely college grad
    (vf['CollGrd'] > 45) & (vf['CollGrd'] <= 65),             # Mixed/some college
    (vf['CollGrd'] > 30) & (vf['CollGrd'] <= 45),             # Likely non-college
    vf['CollGrd'] <= 30,                                       # Definitely non-college
    vf['CollGrd'].isna(),                                      # Missing
]
edu_values = [7, 4, 1, 0, 3]
vf['pts_education'] = np.select(edu_conditions, edu_values, default=3)
print(f"  Factor 6 - Education (max 7): mean={vf['pts_education'].mean():.1f}")

# --- FACTOR 7: Vote Frequency / Perfect Voter (max +5) ---
# Polling: minimal spread (2.7pts) but user says perfect voters are a slight indicator
# De-weighted from v1's max 15 to max 5
freq_conditions = [
    vf['vote_count_6'] == 6,       # Perfect voter
    vf['vote_count_6'] >= 4,       # Frequent
    vf['vote_count_6'] >= 2,       # Occasional
    vf['vote_count_6'] < 2,        # Rare
]
freq_values = [5, 3, 1, 0]
vf['pts_frequency'] = np.select(freq_conditions, freq_values, default=0)
print(f"  Factor 7 - Vote Frequency (max 5): mean={vf['pts_frequency'].mean():.1f}")

# --- FACTOR 8: Party Registration (max +5) ---
# DE-WEIGHTED from v1's max 30 — SF is 64% Dem so this barely discriminates
# Still worth some points since NPP/R are less likely Scott voters
party_map = {'D': 5, 'U': 2, 'R': 0, 'G': 1, 'L': 0, 'P': 1, 'O': 1}
vf['pts_party'] = vf['Party'].map(party_map).fillna(1)
print(f"  Factor 8 - Party (max 5): mean={vf['pts_party'].mean():.1f}")

# ============================================================
# STEP 5: COMPUTE COMPOSITE SCORE
# ============================================================

print("\n" + "=" * 70)
print("STEP 5: COMPUTING COMPOSITE SCORE")
print("=" * 70)

# Sum all factor points
factor_cols = ['pts_ideology', 'pts_lgbtq', 'pts_geography', 'pts_race',
               'pts_age', 'pts_education', 'pts_frequency', 'pts_party']
MAX_RAW_SCORE = 30 + 20 + 15 + 10 + 8 + 7 + 5 + 5  # = 100

vf['raw_score'] = vf[factor_cols].sum(axis=1)

# Raw score IS the support score (max = 100 by design)
vf['support_score'] = vf['raw_score'].clip(0, 100).round(1)

print(f"  Max possible raw score: {MAX_RAW_SCORE}")
print(f"  Raw score range: {vf['raw_score'].min():.0f} - {vf['raw_score'].max():.0f}")
print(f"  Support score: mean={vf['support_score'].mean():.1f}, median={vf['support_score'].median():.1f}")
print(f"  Std dev: {vf['support_score'].std():.1f}")

# Score distribution by decile
print(f"\n  Score distribution (deciles):")
for pct in [10, 20, 30, 40, 50, 60, 70, 80, 90]:
    val = vf['support_score'].quantile(pct / 100)
    print(f"    P{pct:2d}: {val:.1f}")

# Score buckets for initial review
print(f"\n  Score bucket distribution:")
for lo, hi, label in [(0, 20, '0-19'), (20, 40, '20-39'), (40, 60, '40-59'),
                        (60, 80, '60-79'), (80, 101, '80-100')]:
    n = ((vf['support_score'] >= lo) & (vf['support_score'] < hi)).sum()
    pct = n / len(vf) * 100
    bar = "#" * int(pct)
    print(f"    {label:8s}: {n:>8,} ({pct:>5.1f}%) {bar}")

# ============================================================
# STEP 6: CALIBRATION AGAINST REAL VOTER IDS
# ============================================================

print("\n" + "=" * 70)
print("STEP 6: CALIBRATION AGAINST REAL VOTER IDs (soft validation)")
print("=" * 70)

print("  NOTE: VAN ID scores are used as soft validation only.")
print("  They don't discriminate well in all-Dem SF primaries.")
print("  Primary calibration is against polling crosstabs.\n")

# Map real ID scores to numeric
id_score_map = {
    '1 - Strong Supporter': 1,
    '2- Weak Supporter': 2,
    '3 - Undecided': 3,
    '4 - Weak appose': 4,
    '5 - Strong appose': 5,
}
ids['id_numeric'] = ids['Voter_ID_Score'].map(id_score_map)
unmapped = ids['id_numeric'].isna().sum()
if unmapped > 0:
    print(f"  WARNING: {unmapped} IDs could not be mapped. Unmapped values:")
    print(f"    {ids[ids['id_numeric'].isna()]['Voter_ID_Score'].unique()}")

# Join real IDs to voter file
vf_cal = vf.merge(
    ids[['Voter File VANID', 'id_numeric', 'Voter_ID_Score']],
    on='Voter File VANID',
    how='inner'
)
print(f"  Matched {len(vf_cal):,} voters with real IDs")

# --- 6A: Mean synthetic score by real ID bucket ---
print("\n  Mean synthetic support score by real ID bucket:")
print("  " + "-" * 65)
cal_summary = vf_cal.groupby('id_numeric').agg(
    count=('support_score', 'size'),
    mean_score=('support_score', 'mean'),
    median_score=('support_score', 'median'),
    std_score=('support_score', 'std'),
).reset_index()

for _, row in cal_summary.iterrows():
    id_label = {1: 'Strong Support', 2: 'Weak Support', 3: 'Undecided',
                4: 'Weak Oppose', 5: 'Strong Oppose'}[int(row['id_numeric'])]
    bar = "#" * int(row['mean_score'] / 2)
    print(f"    ID {int(row['id_numeric'])} ({id_label:15s}): n={int(row['count']):>3}  "
          f"mean={row['mean_score']:.1f}  median={row['median_score']:.1f}  "
          f"std={row['std_score']:.1f}  {bar}")

# Check monotonicity
means = cal_summary['mean_score'].values
is_monotonic = all(means[i] >= means[i+1] for i in range(len(means)-1))
print(f"\n  Monotonicity check (scores should decrease 1->5): {'PASS' if is_monotonic else 'FAIL (expected — IDs dont discriminate well in Dem primaries)'}")

# Spread between ID 1 and ID 5
if len(means) >= 5:
    spread = means[0] - means[-1]
    print(f"  Spread (ID1 - ID5): {spread:+.1f} points {'(meaningful)' if spread > 3 else '(limited — expected per user direction)'}")

# --- 6B: Factor-level diagnostic ---
print("\n  Factor-level diagnostic (mean points: Strong Support vs Strong Oppose):")
print("  " + "-" * 70)
factor_names = ['ideology', 'lgbtq', 'geography', 'race', 'age', 'education', 'frequency', 'party']
max_pts = [30, 20, 15, 10, 8, 7, 5, 5]
id1 = vf_cal[vf_cal['id_numeric'] == 1]
id5 = vf_cal[vf_cal['id_numeric'] == 5]
print(f"  {'Factor':18s} {'ID1 Mean':>10} {'ID5 Mean':>10} {'Spread':>10} {'Max':>6}")
for fname, maxp in zip(factor_names, max_pts):
    col = f'pts_{fname}'
    m1 = id1[col].mean()
    m5 = id5[col].mean() if len(id5) > 0 else float('nan')
    spread = m1 - m5 if pd.notna(m5) else float('nan')
    flag = " ***" if pd.notna(spread) and abs(spread) > 1 else ""
    print(f"  {fname:18s} {m1:>10.1f} {m5:>10.1f} {spread:>+10.1f} {maxp:>6}{flag}")

# --- 6C: Geographic reweighting (for reference) ---
geo_dist_electorate = vf.groupby('CountySupervisorName').size() / len(vf)
geo_dist_ids = vf_cal.groupby('CountySupervisorName').size() / len(vf_cal)

print("\n  Geographic bias in ID sample:")
print("  " + "-" * 60)
print(f"  {'Sup Dist':>10}  {'ID Sample %':>12}  {'Electorate %':>14}  {'Ratio':>8}")
print("  " + "-" * 60)
for dist in sorted(geo_dist_electorate.index):
    id_pct = geo_dist_ids.get(dist, 0) * 100
    el_pct = geo_dist_electorate[dist] * 100
    ratio = id_pct / el_pct if el_pct > 0 else 0
    flag = " OVER" if ratio > 1.5 else (" UNDER" if ratio < 0.5 else "")
    print(f"    D{int(dist):>2}        {id_pct:>5.1f}%         {el_pct:>5.1f}%      {ratio:.2f}x{flag}")

# Save calibration report
cal_summary.to_csv(os.path.join(OUTPUT_DIR, 'calibration_report.csv'), index=False)
print(f"\n  Calibration report saved to {OUTPUT_DIR}calibration_report.csv")

# ============================================================
# STEP 7: IDENTIFY OPPOSITION (Saikat + MAGA)
# ============================================================

print("\n" + "=" * 70)
print("STEP 7: IDENTIFYING OPPOSITION (SAIKAT SUPPORTERS + MAGA)")
print("=" * 70)

# Opposition is NOT just "low support score" — it's specifically:
# 1. Very progressive voters likely to support Saikat Chakrabarti
# 2. MAGA / Trump supporters
# Both are identified via TargetSmart scores

# MAGA flag: TSMTrumpSup > 50 (TS score where higher = more likely Trump supporter)
vf['is_maga'] = vf['TSMTrumpSup'].fillna(0) > 50
maga_n = vf['is_maga'].sum()
print(f"  MAGA identified (TSMTrumpSup > 50): {maga_n:,} ({maga_n/len(vf)*100:.1f}%)")

# Saikat supporter profile: very progressive + certain demographics
# Key signals from crosstabs: Progressive ideology (TS Ideo >= 90),
# younger voters, non-White non-API
vf['is_saikat_likely'] = (
    (vf['Ideo'].fillna(75) >= 90) &       # Very progressive
    (vf['support_score'] < 55)              # Not scoring as Scott supporter
)
saikat_n = vf['is_saikat_likely'].sum()
print(f"  Saikat-likely identified (Ideo >= 90 & score < 55): {saikat_n:,} ({saikat_n/len(vf)*100:.1f}%)")

# Conservative opposition: moderate-to-conservative who won't vote Dem primary
vf['is_conservative_opp'] = (
    (vf['Ideo'].fillna(75) < 45) |         # Conservative ideology
    ((vf['Party'] == 'R') & (vf['TSMTrumpSup'].fillna(0) > 30))  # Republican leaning
)
con_n = vf['is_conservative_opp'].sum()
print(f"  Conservative opposition identified: {con_n:,} ({con_n/len(vf)*100:.1f}%)")

# ============================================================
# STEP 8: ASSIGN UNIVERSE FLAGS
# ============================================================

print("\n" + "=" * 70)
print("STEP 8: ASSIGNING UNIVERSE FLAGS")
print("=" * 70)

# Individual turnout probability from TargetSmart NonPresPriTO score (0-100 scale)
vf['turnout_probability'] = vf['NonPresPriTO'].fillna(vf['NonPresPriTO'].median())

# Universe assignment logic:
# 1. First, flag explicit opposition (Saikat-likely, MAGA, conservative)
# 2. Then assign by support score thresholds
# 3. This means a high-scoring voter can't be in opposition unless flagged

vf['universe'] = 'Persuasion'  # default

# Base: high support score AND not flagged as opposition
vf.loc[
    (vf['support_score'] >= SUPPORT_BASE_THRESHOLD) &
    ~vf['is_maga'] &
    ~vf['is_saikat_likely'] &
    ~vf['is_conservative_opp'],
    'universe'
] = 'Base'

# Opposition: explicitly identified OR very low support score
vf.loc[vf['is_maga'], 'universe'] = 'Opposition'
vf.loc[vf['is_saikat_likely'], 'universe'] = 'Opposition'
vf.loc[vf['is_conservative_opp'], 'universe'] = 'Opposition'
vf.loc[vf['support_score'] < SUPPORT_PERSUASION_LOW, 'universe'] = 'Opposition'

# Assign support score bucket for reference
vf['support_score_bucket'] = pd.cut(
    vf['support_score'],
    bins=[-0.1, SUPPORT_PERSUASION_LOW, SUPPORT_BASE_THRESHOLD, 100.1],
    labels=['Low', 'Medium', 'High'],
    include_lowest=True
)

# Base drop-off flag: supporters who may not show up
vf['base_dropoff'] = (
    (vf['universe'] == 'Base') &
    (vf['turnout_probability'] < TURNOUT_DROPOFF_THRESHOLD)
)

# Opposition sub-type
vf['opposition_type'] = ''
vf.loc[vf['is_maga'] & (vf['universe'] == 'Opposition'), 'opposition_type'] = 'MAGA'
vf.loc[vf['is_saikat_likely'] & (vf['universe'] == 'Opposition'), 'opposition_type'] = 'Saikat-likely'
vf.loc[vf['is_conservative_opp'] & ~vf['is_maga'] & (vf['universe'] == 'Opposition'), 'opposition_type'] = 'Conservative'
vf.loc[(vf['universe'] == 'Opposition') & (vf['opposition_type'] == ''), 'opposition_type'] = 'Low-score'

# Persuasion priority flags
vf['persuasion_priority'] = False
is_persuasion = vf['universe'] == 'Persuasion'

# Priority 1: API voters in persuasion (housing + ICE/immigration message)
api_flag = is_persuasion & (vf['RaceName'] == 'Asian or Pacific Islander')
vf.loc[api_flag, 'persuasion_priority'] = True

# Priority 2: Jewish identity (TargetSmart Jewish score > 90 ≈ 10% of SF)
jewish_flag = is_persuasion & (vf['Jewish'].fillna(0) > 90)
vf.loc[jewish_flag, 'persuasion_priority'] = True

# Priority 3: Male 18-49 (housing + Trump message)
male_young_flag = is_persuasion & (vf['Sex'] == 'M') & (vf['Age'] >= 18) & (vf['Age'] <= 49)
vf.loc[male_young_flag, 'persuasion_priority'] = True

# Priority 4: AD 19 geography (underperforming)
ad19_flag = is_persuasion & (vf['HD'] == 19)
vf.loc[ad19_flag, 'persuasion_priority'] = True

# Priority 5: Strong renters (housing affordability message, HomeOwner < 20)
renter_flag = is_persuasion & (vf['HomeOwner'].fillna(50) < 20)
vf.loc[renter_flag, 'persuasion_priority'] = True

# ============================================================
# STEP 9: PRINT UNIVERSE SUMMARY
# ============================================================

print("\n" + "=" * 70)
print("STEP 9: UNIVERSE SUMMARY")
print("=" * 70)

total = len(vf)
print(f"\n  Total active electorate (CD-11, Sup Districts 1-10): {total:,}")

# Universe counts
print(f"\n  {'Universe':<15} {'Count':>10} {'% of Total':>12} {'Avg Score':>11} {'Avg Turnout':>13}")
print("  " + "-" * 65)
for univ in ['Base', 'Persuasion', 'Opposition']:
    subset = vf[vf['universe'] == univ]
    n = len(subset)
    pct = n / total * 100
    avg_score = subset['support_score'].mean()
    avg_turnout = subset['turnout_probability'].mean()
    print(f"  {univ:<15} {n:>10,} {pct:>10.1f}%  {avg_score:>10.1f}  {avg_turnout:>10.1f}")

# Check if Base is near 38% target
base_pct = (vf['universe'] == 'Base').sum() / total * 100
print(f"\n  Base % target: 38% (polling True Base)")
print(f"  Base % actual: {base_pct:.1f}%")
if abs(base_pct - 38) < 5:
    print(f"  CALIBRATION: GOOD (within 5pts of target)")
elif abs(base_pct - 38) < 10:
    print(f"  CALIBRATION: FAIR (within 10pts of target)")
else:
    print(f"  CALIBRATION: NEEDS ADJUSTMENT (>{abs(base_pct - 38):.0f}pts from target)")

# Opposition breakdown
print(f"\n  Opposition breakdown:")
for otype in ['Saikat-likely', 'MAGA', 'Conservative', 'Low-score']:
    n = (vf['opposition_type'] == otype).sum()
    print(f"    {otype:20s}: {n:>8,} ({n/total*100:.1f}%)")

# Sub-segments
base_n = (vf['universe'] == 'Base').sum()
persuasion_n = (vf['universe'] == 'Persuasion').sum()
base_dropoff_n = vf['base_dropoff'].sum()
persuasion_priority_n = vf['persuasion_priority'].sum()

print(f"\n  Sub-segments:")
if base_n > 0:
    print(f"    Drop-off Base (supporters w/ turnout < {TURNOUT_DROPOFF_THRESHOLD}): "
          f"{base_dropoff_n:,} ({base_dropoff_n/base_n*100:.1f}% of Base)")
if persuasion_n > 0:
    print(f"    Persuasion Priority (any flag): "
          f"{persuasion_priority_n:,} ({persuasion_priority_n/persuasion_n*100:.1f}% of Persuasion)")

    print(f"\n    Persuasion priority breakdown (voters can be in multiple):")
    print(f"      API voters:         {api_flag.sum():>8,}")
    print(f"      Jewish identity:    {jewish_flag.sum():>8,}")
    print(f"      Male 18-49:         {male_young_flag.sum():>8,}")
    print(f"      AD 19 geography:    {ad19_flag.sum():>8,}")
    print(f"      Non-homeowners:     {renter_flag.sum():>8,}")

# Demographic breakdown per universe
print("\n  Demographic breakdown by universe:")
print("  " + "-" * 75)

for demo_name, demo_col, top_groups in [
    ('Party', 'Party', ['D', 'U', 'R']),
    ('Race', 'RaceName', ['White', 'Asian or Pacific Islander', 'Hispanic or Latino', 'Black']),
    ('Sex', 'Sex', ['F', 'M']),
]:
    print(f"\n  {demo_name}:")
    print(f"  {'':20s} {'Base':>12} {'Persuasion':>12} {'Opposition':>12}")
    for grp in top_groups:
        row = []
        for univ in ['Base', 'Persuasion', 'Opposition']:
            subset = vf[vf['universe'] == univ]
            n_grp = (subset[demo_col] == grp).sum()
            pct = n_grp / len(subset) * 100 if len(subset) > 0 else 0
            row.append(f"{pct:.1f}%")
        print(f"    {grp:18s} {row[0]:>12} {row[1]:>12} {row[2]:>12}")

# Age breakdown
print(f"\n  Age:")
print(f"  {'':20s} {'Base':>12} {'Persuasion':>12} {'Opposition':>12}")
age_bins = [(18, 34, '18-34'), (35, 49, '35-49'), (50, 64, '50-64'), (65, 200, '65+')]
for lo, hi, label in age_bins:
    row = []
    for univ in ['Base', 'Persuasion', 'Opposition']:
        subset = vf[vf['universe'] == univ]
        n_grp = ((subset['Age'] >= lo) & (subset['Age'] <= hi)).sum()
        pct = n_grp / len(subset) * 100 if len(subset) > 0 else 0
        row.append(f"{pct:.1f}%")
    print(f"    {label:18s} {row[0]:>12} {row[1]:>12} {row[2]:>12}")

# Geographic breakdown
print(f"\n  Supervisor District:")
print(f"  {'':20s} {'Base':>12} {'Persuasion':>12} {'Opposition':>12} {'Base %':>10}")
for dist in sorted(vf['CountySupervisorName'].unique()):
    row = []
    for univ in ['Base', 'Persuasion', 'Opposition']:
        subset = vf[vf['universe'] == univ]
        n_grp = (subset['CountySupervisorName'] == dist).sum()
        row.append(n_grp)
    total_dist = sum(row)
    base_pct_d = row[0] / total_dist * 100 if total_dist > 0 else 0
    print(f"    District {int(dist):2d}       {row[0]:>10,}   {row[1]:>10,}   {row[2]:>10,}   {base_pct_d:>8.1f}%")

# Ideology breakdown (mean TS Ideo by universe)
print(f"\n  Mean TS Ideo score by universe:")
for univ in ['Base', 'Persuasion', 'Opposition']:
    subset = vf[vf['universe'] == univ]
    mean_ideo = subset['Ideo'].mean()
    print(f"    {univ:15s}: {mean_ideo:.1f}")

# Calibration vs real IDs
print("\n  Universe assignment vs. real voter IDs (soft validation):")
print("  " + "-" * 60)
vf_cal2 = vf.merge(
    ids[['Voter File VANID', 'Voter_ID_Score']],
    on='Voter File VANID',
    how='inner'
)
id_vs_univ = pd.crosstab(vf_cal2['Voter_ID_Score'], vf_cal2['universe'], margins=True)
for col in ['Base', 'Persuasion', 'Opposition']:
    if col not in id_vs_univ.columns:
        id_vs_univ[col] = 0
cols_present = [c for c in ['Base', 'Persuasion', 'Opposition', 'All'] if c in id_vs_univ.columns]
id_vs_univ = id_vs_univ[cols_present]
print(id_vs_univ.to_string())

# ============================================================
# STEP 10: SAVE OUTPUT
# ============================================================

print("\n" + "=" * 70)
print("STEP 10: SAVING OUTPUT")
print("=" * 70)

output_cols = [
    # Identifiers
    'Voter File VANID', 'LastName', 'FirstName',
    'mAddress', 'mCity', 'mZip5',
    # Demographics
    'Age', 'Sex', 'RaceName', 'Party', 'HD',
    'PrecinctName', 'CountySupervisorName',
    # Scores (all on 0-100 scale)
    'support_score', 'support_score_bucket', 'turnout_probability',
    'vote_frequency_score', 'raw_score', 'vote_count_6',
    # Factor breakdown
    'pts_ideology', 'pts_lgbtq', 'pts_geography', 'pts_race',
    'pts_age', 'pts_education', 'pts_frequency', 'pts_party',
    # Universe flags
    'universe', 'base_dropoff', 'persuasion_priority',
    'opposition_type', 'is_maga', 'is_saikat_likely', 'is_conservative_opp',
    # Key TargetSmart scores
    'NonPresPriTO', 'Ideo', 'HomeOwner', 'CollGrd', 'MarEqu',
    'TSMHarrisSupp', 'TSMTrumpSup',
]

output_cols = [c for c in output_cols if c in vf.columns]
vf_out = vf[output_cols].copy()

output_path = os.path.join(OUTPUT_DIR, 'cd11_voters_with_scores.csv')
vf_out.to_csv(output_path, index=False)
print(f"  Saved {len(vf_out):,} voters to {output_path}")
print(f"  File size: {os.path.getsize(output_path) / 1024 / 1024:.1f} MB")

# Save universe summary
univ_summary = vf.groupby('universe').agg(
    count=('support_score', 'size'),
    mean_score=('support_score', 'mean'),
    median_score=('support_score', 'median'),
    mean_turnout=('turnout_probability', 'mean'),
    pct_dem=('Party', lambda x: (x == 'D').mean() * 100),
    pct_api=('RaceName', lambda x: (x == 'Asian or Pacific Islander').mean() * 100),
    pct_female=('Sex', lambda x: (x == 'F').mean() * 100),
    mean_age=('Age', 'mean'),
    mean_ideo=('Ideo', 'mean'),
).reset_index()
univ_summary.to_csv(os.path.join(OUTPUT_DIR, 'universe_summary.csv'), index=False)

print("\n" + "=" * 70)
print("DONE — Tasks 1 & 2 complete (v2). Review the summary above.")
print("Awaiting approval before proceeding to Tasks 3-5.")
print("=" * 70)
