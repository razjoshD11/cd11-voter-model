#!/usr/bin/env python3
"""
=============================================================================
RUN ALL — SF CD-11 Voter Turnout Model Pipeline
=============================================================================

This script runs every step of the turnout model in order:

  Step 1: Build precinct universe from VAN voter file
  Step 2: Pull historical turnout from electionmapsf.com
  Step 3: Calibrate model using poll crosstabs
  Step 4: Build turnout scenarios (LOW / EXPECTED / HIGH)
  Step 5: Aggregate to geographic levels (Citywide, CD11, Sup Districts)
  Step 6: Generate interactive HTML dashboard

Usage:
  python run_all.py            # Run all steps
  python run_all.py --from 4   # Re-run from step 4 onward (skips steps 1-3)

Each step reads from data/processed/ and writes back to data/processed/.
The final output is dashboard/turnout_dashboard.html.
=============================================================================
"""

import subprocess
import sys
import os
import time

# ---------------------------------------------------------------------------
# SETUP: Find the project root directory (where this script lives)
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")

# The 6 steps in order. Each entry is (step_number, filename, description).
STEPS = [
    (1, "01_build_precinct_universe.py", "Build precinct universe from voter file"),
    (2, "02_calculate_historical_rates.py", "Pull historical turnout & calculate rates"),
    (3, "03_calibrate_from_polls.py", "Calibrate model from poll crosstabs"),
    (4, "04_build_scenarios.py", "Build turnout scenarios (LOW/EXPECTED/HIGH)"),
    (5, "05_aggregate.py", "Aggregate to geographic levels"),
    (6, "06_build_dashboard.py", "Generate interactive HTML dashboard"),
]


def run_step(step_num, filename, description):
    """Run a single pipeline step and check for errors."""
    script_path = os.path.join(SCRIPTS_DIR, filename)

    print(f"\n{'='*70}")
    print(f"  STEP {step_num}/6: {description}")
    print(f"  Running: {filename}")
    print(f"{'='*70}\n")

    start = time.time()

    # Run the script as a subprocess so each step is isolated
    result = subprocess.run(
        [sys.executable, script_path],
        cwd=PROJECT_ROOT,
        capture_output=False,  # Let output flow to terminal
    )

    elapsed = time.time() - start

    if result.returncode != 0:
        print(f"\n*** STEP {step_num} FAILED (exit code {result.returncode}) ***")
        print(f"Fix the error above, then re-run:  python run_all.py --from {step_num}")
        sys.exit(1)

    print(f"\n  Step {step_num} completed in {elapsed:.1f}s")


def main():
    # Parse optional --from argument
    start_from = 1
    if "--from" in sys.argv:
        idx = sys.argv.index("--from")
        if idx + 1 < len(sys.argv):
            try:
                start_from = int(sys.argv[idx + 1])
            except ValueError:
                print("Error: --from requires a step number (1-6)")
                sys.exit(1)

    print("=" * 70)
    print("  SF CD-11 VOTER TURNOUT MODEL — FULL PIPELINE")
    print("  Scott Wiener for Congress, 2026 Cycle")
    print("=" * 70)

    if start_from > 1:
        print(f"\n  Skipping steps 1-{start_from - 1}, starting from step {start_from}")

    total_start = time.time()

    for step_num, filename, description in STEPS:
        if step_num < start_from:
            continue
        run_step(step_num, filename, description)

    total_elapsed = time.time() - total_start

    print(f"\n{'='*70}")
    print(f"  ALL STEPS COMPLETE — Total time: {total_elapsed:.1f}s")
    print(f"")
    print(f"  Dashboard: dashboard/turnout_dashboard.html")
    print(f"  Open it in your browser to explore the results.")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
