import pandas as pd
from datetime import datetime, timedelta

# --- CONFIG ---
CSV_PATH    = "alerts.csv"
DATE_COL    = "Alert Date"
DATE_FORMAT = "%m/%d/%Y %I:%M:%S %p"

KNOWN_STATUSES = {"open", "closed", "in progress", "pending", "resolved", "escalated"}

# ----------------------------------------

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

    return monday, sunday


def load_csv(path):
    try:
        df = pd.read_csv(path)
        print(f"  Loaded {len(df)} total rows from CSV.")
        return df
    except FileNotFoundError:
        print(f"ERROR: File not found → {path}")
        exit()


def get_biz_days(start, end):
    n   = 0
    cur = start.date() + timedelta(days=1)
    while cur <= end.date():
        if cur.weekday() < 5:
            n += 1
        cur += timedelta(days=1)
    return n


def safe_parse(series):
    return pd.to_datetime(series, errors='coerce')


def is_suspicious(val):
    if pd.isna(val):
        return True
    s = str(val).strip().lower()
    return s in ['', '_empty', 'n/a', 'none', 'null', 'unknown', '-', 'na'] or len(s) <= 1


def get_sid_num(sid):
    if pd.isna(sid):
        return None
    digits = ''.join(filter(str.isdigit, str(sid)))
    return int(digits) if digits else None


def deep_analysis(day_df, day_name, day_dt, full_df):
    print(f"\n{'='*62}")
    print(f"  DEEP ANALYSIS — {day_name}  {day_dt.strftime('%m/%d/%Y')}")
    print(f"{'='*62}")
    print(f"  Records on this day: {len(day_df)}")

    day_df = day_df.copy()

    # Pre-parse all date columns
    day_df['_alert_dt']  = safe_parse(day_df['Alert Date'])
    day_df['_action_dt'] = safe_parse(day_df['Action Date'])            if 'Action Date'            in day_df.columns else pd.NaT
    day_df['_comp_dt']   = safe_parse(day_df['AnalysisCompletionDate']) if 'AnalysisCompletionDate' in day_df.columns else pd.NaT
    day_df['_pr_start']  = safe_parse(day_df['Peer_Review_Start'])      if 'Peer_Review_Start'      in day_df.columns else pd.NaT
    day_df['_pr_end']    = safe_parse(day_df['Peer_Review_End'])        if 'Peer_Review_End'        in day_df.columns else pd.NaT
    day_df['_sid_num']   = day_df['Session ID'].apply(get_sid_num)

    # ── LAYER 1: Sequential Anomaly ──────────────────────────
    print(f"\n  [Layer 1] Sequential Anomaly")
    print(f"  Logic: if SID 101 and 103 are both {day_dt.strftime('%m/%d/%Y')},")
    print(f"         SID 102 should not say a different date.")

    l1_issues = []

    # Build a sorted view of the ENTIRE week by SID so we can check neighbours
    fdf = full_df.copy()
    fdf['_sid_num']   = fdf['Session ID'].apply(get_sid_num)
    fdf['_alert_dt']  = safe_parse(fdf['Alert Date'])
    fdf['_alert_date'] = fdf['_alert_dt'].dt.date
    fdf = fdf.dropna(subset=['_sid_num']).sort_values('_sid_num').reset_index(drop=True)

    for idx, row in fdf.iterrows():
        this_date = row['_alert_date']
        this_sid  = row['_sid_num']
        this_id   = row['Session ID']

        # Get previous and next records in SID order
        prev_row = fdf.iloc[idx - 1] if idx > 0               else None
        next_row = fdf.iloc[idx + 1] if idx < len(fdf) - 1    else None

        prev_date = prev_row['_alert_date'] if prev_row is not None else None
        next_date = next_row['_alert_date'] if next_row is not None else None
        prev_id   = prev_row['Session ID']  if prev_row is not None else None
        next_id   = next_row['Session ID']  if next_row is not None else None

        # Both neighbours exist and agree on a date that differs from this record
        if prev_date is not None and next_date is not None:
            if prev_date == next_date and prev_date != this_date:
                l1_issues.append(
                    f"    ⚠ {this_id} says {this_date} BUT "
                    f"neighbours {prev_id} and {next_id} both say {prev_date}\n"
                    f"       → Likely mis-dated, should probably be {prev_date}"
                )

        # One neighbour agrees with the other side and this record is the odd one out
        elif prev_date is not None and prev_date != this_date:
            if next_date is None:
                l1_issues.append(
                    f"    ⚠ {this_id} says {this_date} but previous "
                    f"{prev_id} says {prev_date} — possible bleed at end of day"
                )
        elif next_date is not None and next_date != this_date:
            if prev_date is None:
                l1_issues.append(
                    f"    ⚠ {this_id} says {this_date} but next "
                    f"{next_id} says {next_date} — possible bleed at start of day"
                )

    if l1_issues:
        print(f"  ⚠ Sequence mismatches found:")
        for s in l1_issues:
            print(s)
    else:
        print("  ✓ All Session IDs are consistent with their Alert Dates")

    # ── LAYER 2: Bleed / Timing Gaps ─────────────────────────
    print(f"\n  [Layer 2] Bleed / Timing Gaps")
    l2_issues = []

    for _, r in day_df.iterrows():
        sid = r['Session ID']

        if pd.notna(r['_alert_dt']) and pd.notna(r['_action_dt']):
            gap = get_biz_days(r['_alert_dt'], r['_action_dt'])
            if gap > 1:
                l2_issues.append(f"    {sid}: Alert→Action = {gap} biz days"
                                 f"  ({r['Alert Date']} → {r.get('Action Date','')})")

        if pd.notna(r['_action_dt']) and pd.notna(r['_comp_dt']):
            gap = get_biz_days(r['_action_dt'], r['_comp_dt'])
            if gap > 2:
                l2_issues.append(f"    {sid}: Action→Completion = {gap} biz days"
                                 f"  ({r.get('Action Date','')} → {r.get('AnalysisCompletionDate','')})")

        if pd.notna(r['_comp_dt']) and pd.notna(r['_pr_start']):
            gap = get_biz_days(r['_comp_dt'], r['_pr_start'])
            if gap > 2:
                l2_issues.append(f"    {sid}: Completion→Peer Review Start = {gap} biz days"
                                 f"  ({r.get('AnalysisCompletionDate','')} → {r.get('Peer_Review_Start','')})")

    if l2_issues:
        print("  ⚠ Timing gaps detected:")
        for s in l2_issues:
            print(s)
    else:
        print("  ✓ No unusual timing gaps")

    # ── LAYER 3: Timeline Logic Violations ───────────────────
    print(f"\n  [Layer 3] Timeline Logic Violations")
    l3_issues = []

    for _, r in day_df.iterrows():
        sid = r['Session ID']

        if pd.notna(r['_action_dt']) and pd.notna(r['_alert_dt']):
            if r['_action_dt'].date() < r['_alert_dt'].date():
                l3_issues.append(
                    f"    ✗ {sid}: Action Date ({r.get('Action Date','')}) is BEFORE "
                    f"Alert Date ({r['Alert Date']}) — this is impossible, "
                    f"you cannot act before the alert exists"
                )

        if pd.notna(r['_comp_dt']) and pd.notna(r['_action_dt']):
            if r['_comp_dt'].date() < r['_action_dt'].date():
                l3_issues.append(
                    f"    ✗ {sid}: Completion ({r.get('AnalysisCompletionDate','')}) is BEFORE "
                    f"Action Date ({r.get('Action Date','')}) — impossible"
                )

        if pd.notna(r['_pr_end']) and pd.notna(r['_pr_start']):
            if r['_pr_end'].date() < r['_pr_start'].date():
                l3_issues.append(
                    f"    ✗ {sid}: Peer Review End ({r.get('Peer_Review_End','')}) is BEFORE "
                    f"Start ({r.get('Peer_Review_Start','')}) — impossible"
                )

    if l3_issues:
        print("  ⚠ Impossible timeline violations:")
        for s in l3_issues:
            print(s)
    else:
        print("  ✓ No timeline logic violations")

    # ── LAYER 4: Empty / Suspicious Fields ───────────────────
    print(f"\n  [Layer 4] Empty / Suspicious Fields")
    CRIT_FIELDS = ['Alert Rule', 'ACF2ID', 'Analyst Name', 'Sign-off status', 'Status']
    l4_issues   = []

    for _, r in day_df.iterrows():
        sid = r['Session ID']
        for f in CRIT_FIELDS:
            if f not in day_df.columns:
                continue
            val = r.get(f, '')
            if is_suspicious(val):
                l4_issues.append(f"    {sid}: '{f}' is empty/suspicious  →  '{val}'")
            elif f == 'Status' and str(val).strip().lower() not in KNOWN_STATUSES:
                l4_issues.append(f"    {sid}: 'Status' = '{val}'  ← not a recognised value")

    if l4_issues:
        print("  ⚠ Field issues found:")
        for s in l4_issues:
            print(s)
    else:
        print("  ✓ All critical fields look good")

    print(f"\n  ► Suggested Action:")
    print(f"    1. Filter SharePoint by Alert Date = {day_dt.strftime('%m/%d/%Y')}")
    print(f"    2. Cross-reference flagged Session IDs above")
    print(f"    3. Check adjacent days for any bleed-over entries")


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
    pb_total = int(input("\nHow many alerts does PowerBI show this week? ").strip())

    # --- Step 3: Load + filter CSV ---
    print(f"\nReading {CSV_PATH}...")
    df = load_csv(CSV_PATH)

    df[DATE_COL] = pd.to_datetime(df[DATE_COL], format=DATE_FORMAT, errors='coerce')
    bad_dates    = df[DATE_COL].isna().sum()
    if bad_dates:
        print(f"  ⚠ Warning: {bad_dates} row(s) had unreadable dates and were skipped.")

    df = df.dropna(subset=[DATE_COL])

    monday_ts = pd.Timestamp(monday)
    sunday_ts = pd.Timestamp(sunday) + pd.Timedelta(hours=23, minutes=59, seconds=59)

    week_df  = df[(df[DATE_COL] >= monday_ts) & (df[DATE_COL] <= sunday_ts)]
    sp_total = len(week_df)

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
        count           = (week_df[DATE_COL].dt.date == day.date()).sum()
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

        pp        = int(raw)
        sp        = sp_by_day[name]
        pp_total += pp
        day_diff  = pp - sp

        if day_diff == 0:
            status = "✓ Match"
        elif day_diff > 0:
            status = f"✗ SP -{day_diff}"
        else:
            status = f"✗ SP +{abs(day_diff)}"

        print(f"  {name:<12} {day.strftime('%m/%d/%Y'):<13} {pp:>10} {sp:>11} {status:>12}")

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

        # --- Step 8: Deep analysis ---
        print()
        go_deep = input("Run deep analysis on discrepancy days? (y/n): ").strip().lower()
        if go_deep == 'y':
            for name, day, pp, sp, d in issues:
                day_df = week_df[week_df[DATE_COL].dt.date == day.date()].copy()
                deep_analysis(day_df, name, day, df)

    print("\nDone.")


if __name__ == "__main__":
    main()
