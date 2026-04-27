import pandas as pd
from datetime import datetime, timedelta

# --- CONFIG ---
CSV_PATH        = "alerts.csv"
DATE_COL        = "Alert Date"
DATE_FORMAT     = "%m/%d/%Y %I:%M:%S %p"

# ----------------------------------------

def get_week_range():
    today   = datetime.today()
    monday  = today - timedelta(days=today.weekday())
    sunday  = monday + timedelta(days=6)

    print(f"\nCurrent week detected: "
          f"{monday.strftime('%m/%d/%Y')} (Mon) — "
          f"{sunday.strftime('%m/%d/%Y')} (Sun)")
    choice = input("Use this week? (y/n): ").strip().lower()

    if choice != 'y':
        raw = input("Enter Monday date (MM/DD/YYYY): ").strip()
        monday = datetime.strptime(raw, "%m/%d/%Y")
        sunday = monday + timedelta(days=6)

    return monday.date(), sunday.date()


def load_csv(path):
    try:
        df = pd.read_csv(path)
        print(f"  Loaded {len(df)} total rows from CSV.")
        return df
    except FileNotFoundError:
        print(f"ERROR: File not found → {path}")
        exit()


def main():
    print("\n" + "=" * 50)
    print("     ALERT RECONCILIATION TOOL")
    print("=" * 50)

    # --- Step 1: Week range ---
    monday, sunday = get_week_range()
    days      = [monday + timedelta(days=i) for i in range(7)]
    day_names = ["Monday","Tuesday","Wednesday",
                 "Thursday","Friday","Saturday","Sunday"]

    # --- Step 2: PowerBI count ---
    pb_total = input("\nHow many alerts does PowerBI show this week? ").strip()
    pb_total = int(pb_total)

    # --- Step 3: Load + filter CSV ---
    print(f"\nReading {CSV_PATH}...")
    df = load_csv(CSV_PATH)

    df[DATE_COL]   = pd.to_datetime(df[DATE_COL],
                                    format=DATE_FORMAT,
                                    errors='coerce')
    bad_dates      = df[DATE_COL].isna().sum()
    if bad_dates:
        print(f"  ⚠ Warning: {bad_dates} row(s) had unreadable dates and were skipped.")

    df['_date']    = df[DATE_COL].dt.date
    week_df        = df[(df['_date'] >= monday) & (df['_date'] <= sunday)]
    sp_total       = len(week_df)

    # --- Step 4: Summary ---
    print("\n" + "=" * 50)
    print(f"  WEEK: {monday.strftime('%m/%d')} – {sunday.strftime('%m/%d/%Y')}")
    print("=" * 50)
    print(f"  PowerBI Total    : {pb_total}")
    print(f"  SharePoint Total : {sp_total}")

    diff = pb_total - sp_total
    if diff == 0:
        print("  ✓ Totals MATCH")
    elif diff > 0:
        print(f"  ✗ SharePoint is MISSING {diff} alert(s)")
    else:
        print(f"  ✗ SharePoint has {abs(diff)} EXTRA alert(s) — possible duplicates or wrong date")

    # --- Step 5: Per-day SharePoint counts ---
    print("\n" + "-" * 46)
    print(f"  {'Day':<12} {'Date':<13} {'SharePoint':>10}")
    print("-" * 46)

    sp_by_day = {}
    for day, name in zip(days, day_names):
        count          = len(week_df[week_df['_date'] == day])
        sp_by_day[name] = count
        print(f"  {name:<12} {day.strftime('%m/%d/%Y'):<13} {count:>10}")

    print("-" * 46)
    print(f"  {'TOTAL':<25} {sp_total:>10}\n")

    # --- Step 6: Optional Proofpoint input ---
    go = input("Enter Proofpoint counts per day to compare? (y/n): ").strip().lower()
    if go != 'y':
        print("\nDone. Run again anytime.")
        return

    print("\n" + "=" * 62)
    print(f"  {'Day':<12} {'Date':<13} {'Proofpoint':>10} "
          f"{'SharePoint':>11} {'Status':>12}")
    print("=" * 62)

    issues   = []
    pp_total = 0

    for day, name in zip(days, day_names):
        raw = input(f"  {name} ({day.strftime('%m/%d')}) — "
                    f"Proofpoint count (Enter to skip): ").strip()

        if raw == '':
            print(f"    → Skipped")
            continue

        pp = int(raw)
        sp = sp_by_day[name]
        pp_total += pp
        day_diff  = pp - sp

        if day_diff == 0:
            status = "✓ Match"
        elif day_diff > 0:
            status = f"✗ SP -{day_diff}"
        else:
            status = f"✗ SP +{abs(day_diff)}"

        print(f"  {name:<12} {day.strftime('%m/%d/%Y'):<13} "
              f"{pp:>10} {sp:>11} {status:>12}")

        if day_diff != 0:
            issues.append((name, day, pp, sp, day_diff))

    print("-" * 62)
    print(f"  {'TOTAL':<25} {pp_total:>10} {sp_total:>11}\n")

    # --- Step 7: Issue summary ---
    if not issues:
        print("✓ All days match. No discrepancies found.")
    else:
        print("⚠  DISCREPANCIES FOUND:")
        print("-" * 62)
        for name, day, pp, sp, d in issues:
            date_str = day.strftime('%m/%d')
            if d > 0:
                print(f"  {name} ({date_str}): SharePoint MISSING {d} alert(s) "
                      f"[PP={pp} vs SP={sp}]")
                print(f"    → Check: wrong date entered, alert not logged, "
                      f"or logged to different week")
            else:
                print(f"  {name} ({date_str}): SharePoint has {abs(d)} EXTRA alert(s) "
                      f"[PP={pp} vs SP={sp}]")
                print(f"    → Check: duplicate entry or wrong date used")

    print("\nDone.")


if __name__ == "__main__":
    main()
