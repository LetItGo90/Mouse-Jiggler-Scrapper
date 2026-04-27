import pandas as pd
from datetime import datetime, timedelta

CSV_PATH = "alerts.csv"  # ← change this
DATE_COL = "Alert Date"  # ← change if your column is named differently

def get_week_range():
    today  = datetime.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    print(f"\nCurrent week detected: "
          f"{monday.strftime('%m/%d/%Y')} (Mon) — "
          f"{sunday.strftime('%m/%d/%Y')} (Sun)")
    choice = input("Use this week? (y/n): ").strip().lower()

    if choice != 'y':
        raw    = input("Enter Monday date (MM/DD/YYYY): ").strip()
        monday = datetime.strptime(raw, "%m/%d/%Y")
        sunday = monday + timedelta(days=6)

    return monday, sunday  # ← returns datetime now, NOT .date()

def main():
    print("\n" + "="*50)
    print("     ALERT RECONCILIATION TOOL")
    print("="*50)

    monday, sunday = get_week_range()
    days      = [monday + timedelta(days=i) for i in range(7)]
    day_names = ["Monday","Tuesday","Wednesday",
                 "Thursday","Friday","Saturday","Sunday"]

    pb_total = int(input("\nHow many alerts does PowerBI show this week? ").strip())

    print(f"\nReading {CSV_PATH}...")
    try:
        df = pd.read_csv(CSV_PATH)
    except FileNotFoundError:
        print(f"ERROR: File not found → {CSV_PATH}")
        return

    print(f"  Loaded {len(df)} rows.")

    # Parse dates — coerce bad ones to NaT
    df['_date'] = pd.to_datetime(df[DATE_COL], errors='coerce')
    bad = df['_date'].isna().sum()
    if bad:
        print(f"  ⚠ {bad} row(s) skipped (bad dates).")
    df = df.dropna(subset=['_date'])

    # ✅ FIX: use pd.Timestamp so types match
    monday_ts = pd.Timestamp(monday)
    sunday_ts = pd.Timestamp(sunday) + pd.Timedelta(hours=23, minutes=59, seconds=59)

    week_df  = df[(df['_date'] >= monday_ts) & (df['_date'] <= sunday_ts)]
    sp_total = len(week_df)

    print("\n" + "="*50)
    print(f"  WEEK: {monday.strftime('%m/%d')} – {sunday.strftime('%m/%d/%Y')}")
    print("="*50)
    print(f"  PowerBI Total    : {pb_total}")
    print(f"  SharePoint Total : {sp_total}")

    diff = pb_total - sp_total
    if diff == 0:
        print("  ✓ Totals MATCH")
    elif diff > 0:
        print(f"  ✗ SharePoint MISSING {diff} alert(s)")
    else:
        print(f"  ✗ SharePoint has {abs(diff)} EXTRA alert(s)")

    print("\n" + "-"*46)
    print(f"  {'Day':<12} {'Date':<13} {'SharePoint':>10}")
    print("-"*46)

    sp_by_day = {}
    for day, name in zip(days, day_names):
        count = (week_df['_date'].dt.date == day.date()).sum()
        sp_by_day[name] = count
        print(f"  {name:<12} {day.strftime('%m/%d/%Y'):<13} {count:>10}")

    print("-"*46)
    print(f"  {'TOTAL':<25} {sp_total:>10}\n")

    go = input("Enter Proofpoint counts per day? (y/n): ").strip().lower()
    if go != 'y':
        print("\nDone.")
        return

    print("\n" + "="*62)
    print(f"  {'Day':<12} {'Date':<13} {'Proofpoint':>10} "
          f"{'SharePoint':>11} {'Status':>12}")
    print("="*62)

    issues   = []
    pp_total = 0

    for day, name in zip(days, day_names):
        raw = input(f"  {name} ({day.strftime('%m/%d')}) — "
                    f"Proofpoint count (Enter to skip): ").strip()
        if raw == '':
            continue

        pp       = int(raw)
        sp       = sp_by_day[name]
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

    print("-"*62)
    print(f"  {'TOTAL':<25} {pp_total:>10} {sp_total:>11}\n")

    if not issues:
        print("✓ All days match.")
    else:
        print("⚠  DISCREPANCIES FOUND:")
        for name, day, pp, sp, d in issues:
            ds = day.strftime('%m/%d')
            if d > 0:
                print(f"  {name} ({ds}): SP MISSING {d} [PP={pp} vs SP={sp}]")
            else:
                print(f"  {name} ({ds}): SP EXTRA {abs(d)} [PP={pp} vs SP={sp}]")

    print("\nDone.")

if __name__ == "__main__":
    main()
