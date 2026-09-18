"""
run_etl.py — single entry point for the whole pipeline.

Wraps load_fact_pl.py, load_fact_class_metric.py, and load_fact_balance_sheet.py
into one script, now that each has been individually proven (Phase 6c/6d/6e).
Plug in a quarterly workbook, get it matched and loaded into all three fact
tables in one run.

This does NOT reimplement any extraction/loading logic -- it imports the
three already-tested modules and calls their functions in sequence, so a
fix to any one loader automatically applies here too, with nothing to
keep in sync by hand.

Usage:
  python run_etl.py path/to/workbook.xlsx --dry-run
      Runs all three extractors, prints a combined summary. No DB writes.
      Always run this first on a file you haven't loaded before.

  python run_etl.py path/to/workbook.xlsx
      Runs all three loaders for real, then runs validate.py automatically
      at the end so you see pass/fail on the same run, not a separate step.

  python run_etl.py path/to/workbook.xlsx --skip-validate
      Same as above but skips the automatic validation pass (e.g. if you
      want to load multiple quarters back-to-back and validate once at
      the end instead of after every file).
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import load_fact_pl
import load_fact_class_metric
import load_fact_balance_sheet


def run_dry_run(workbook_path):
    print("#" * 70)
    print(f"# DRY RUN: {os.path.basename(workbook_path)}")
    print("#" * 70)

    print("\n" + "=" * 70)
    print("fact_pl (IFRS17 P&L + combined premium summaries)")
    print("=" * 70)
    load_fact_pl.dry_run(workbook_path)

    print("\n" + "=" * 70)
    print("fact_class_metric (LT revenue accounts, GB/Micro class metrics)")
    print("=" * 70)
    load_fact_class_metric.dry_run(workbook_path)

    print("\n" + "=" * 70)
    print("fact_balance_sheet (LT/GB/Micro capital structure)")
    print("=" * 70)
    load_fact_balance_sheet.dry_run(workbook_path)

    print("\n" + "#" * 70)
    print("# DRY RUN COMPLETE -- nothing written to any database.")
    print("# Review the three sections above, then re-run without --dry-run")
    print("# to actually load.")
    print("#" * 70)


def run_real_load(workbook_path, skip_validate):
    print("#" * 70)
    print(f"# LOADING: {os.path.basename(workbook_path)}")
    print("#" * 70)

    results = {}

    print("\n" + "=" * 70)
    print("[1/3] Loading fact_pl...")
    print("=" * 70)
    try:
        load_fact_pl.load_to_db(workbook_path)
        results["fact_pl"] = "OK"
    except Exception as e:
        results["fact_pl"] = f"FAILED: {e}"
        print(f"fact_pl load failed: {e}")

    print("\n" + "=" * 70)
    print("[2/3] Loading fact_class_metric...")
    print("=" * 70)
    try:
        load_fact_class_metric.load_to_db(workbook_path)
        results["fact_class_metric"] = "OK"
    except Exception as e:
        results["fact_class_metric"] = f"FAILED: {e}"
        print(f"fact_class_metric load failed: {e}")

    print("\n" + "=" * 70)
    print("[3/3] Loading fact_balance_sheet...")
    print("=" * 70)
    try:
        load_fact_balance_sheet.load_to_db(workbook_path)
        results["fact_balance_sheet"] = "OK"
    except Exception as e:
        results["fact_balance_sheet"] = f"FAILED: {e}"
        print(f"fact_balance_sheet load failed: {e}")

    print("\n" + "#" * 70)
    print("# LOAD SUMMARY")
    print("#" * 70)
    for table, status in results.items():
        print(f"  {table}: {status}")

    any_failed = any("FAILED" in v for v in results.values())

    if skip_validate:
        print("\n(--skip-validate set: skipping validation pass)")
    else:
        print("\n" + "#" * 70)
        print("# Running validation pass...")
        print("#" * 70)
        validate_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "validate.py")
        subprocess.run([sys.executable, validate_path])

    if any_failed:
        print("\nWARNING: one or more loaders failed. Check output above before trusting this data.")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook_path")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-validate", action="store_true",
                         help="Skip the automatic validation pass after loading")
    args = parser.parse_args()

    if args.dry_run:
        run_dry_run(args.workbook_path)
    else:
        run_real_load(args.workbook_path, args.skip_validate)
