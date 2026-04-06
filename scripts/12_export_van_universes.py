#!/usr/bin/env python3
"""
12_export_van_universes.py

Exports a CSV file for VAN upload with VAN IDs and universe assignment columns.
Each voter gets an 'X' in exactly one universe column (Base, Persuasion, Opposition)
plus an optional 'X' in Base Drop-off if applicable.

Output: /Users/joshraznick/Desktop/Claude/cd11_van_universes.csv
"""

import pandas as pd
import os

INPUT = '/Users/joshraznick/Desktop/Claude/turnout_model/data/processed/cd11_voters_with_scores.csv'
OUTPUT = '/Users/joshraznick/Desktop/Claude/cd11_van_universes.csv'

print("Loading voter scores ...")
df = pd.read_csv(INPUT, low_memory=False)
print(f"  {len(df):,} voters loaded")

# Build the VAN upload columns
out = pd.DataFrame()
out['Voter File VANID'] = df['Voter File VANID']
out['Base'] = (df['universe'] == 'Base').map({True: 'X', False: ''})
out['Persuasion'] = (df['universe'] == 'Persuasion').map({True: 'X', False: ''})
out['Opposition'] = (df['universe'] == 'Opposition').map({True: 'X', False: ''})
out['Base Drop-off'] = df['base_dropoff'].map({True: 'X', False: ''})

# Summary
for col in ['Base', 'Persuasion', 'Opposition', 'Base Drop-off']:
    n = (out[col] == 'X').sum()
    print(f"  {col}: {n:,} voters")

out.to_csv(OUTPUT, index=False)
print(f"\nSaved to: {OUTPUT}")
print(f"File size: {os.path.getsize(OUTPUT) / 1024 / 1024:.1f} MB")
print(f"Columns: {list(out.columns)}")
