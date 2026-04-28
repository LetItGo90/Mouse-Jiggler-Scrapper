import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta

# ==============================================================
#   Proofpoint vs SharePoint Counter + Discrepancy Analyzer
# ==============================================================

DEFAULT_CSV_PATH = "./alerts_export.csv"

# ---- HELPERS ----

def get_week_dates():
    today = datetime.today()
    dow = today.weekday()  # Monday=0
    monday = today - timedelta(days=dow)
    return [monday + timedelta(days=i) for i in range(7)]

def get_biz_day_diff(from_date, to_date):
    n = 0
    cur = from_date.date() + timedelta(days=1)
    while cur <= to_date.date():
        if cur.weekday() < 5:
            n += 1
        cur += timedelta(days=1)
    return n

def is_suspicious(val):
    if pd.isna(val) or str(val).strip() == '':
        return True
    t = str(val).strip().lower()
    return t in ['_empty','n/a','none','null','unknown','-','na'] or len(t) <= 1

def get_session_num(sid):
    if pd.isna(sid):
        return 0
    num = ''.join(filter(str.isdigit, str(sid)))
    return int(num) if num else 0

# ---- LOAD CSV ----

csv_path = DEFAULT_CSV_PATH
if not os.path.exists(csv_path):
    csv_path = input("CSV not found. Enter path to alerts_export.csv: ").strip()
    if not os.path.exists(csv_path):
        print("File not found. Exiting.")
        exit()

df = pd.read_csv(csv_path)
df['Alert Date'] = pd.to_datetime(df['Alert Date'], errors='coerce')

week_dates = get_week_dates()
day_names  = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']

# ---- COUNT SP PER DAY ----

sp_counts = {}
for i, d in enumerate(week_dates):
    sp_counts[i] = len(df[df['Alert Date'].dt.date == d.date()])

total_sp = sum(sp_counts.values())

print()
print("─" * 54)
print(f"  SharePoint Total this week: {total_sp}")
print("─" * 54)

# ---- ENTER PP COUNTS ----

yn = input("\nEnter Proofpoint counts per day? (y/n): ").strip().lower()
if yn != 'y':
    print("Done.")
    exit()

print()
print("=" * 60)
print(f"{'Day':<12}{'Date':<14}{'Proofpoint':<12}{'SharePoint':<12}Status")
print("=" * 60)

pp_counts = {}
for i, d in enumerate(week_dates):
    name = day_names[i]
    raw  = input(f"  {name} ({d.strftime('%m/%d')}) - PP count (Enter to skip): ").strip()

    if not raw:
        pp_counts[i] = None
        continue

    pp = int(raw)
    sp = sp_counts[i]
    pp_counts[i] = pp

    diff = sp - pp
    if diff == 0:
        status = "✓"
    elif diff > 0:
        status = f"X  SP +{diff}"
    else:
        status = f"X  PP +{abs(diff)}"

    print(f"  {name:<12}{d.strftime('%m/%d/%Y'):<14}{pp:<12}{sp:<12}{status}")

total_pp = sum(v for v in pp_counts.values() if v is not None)
print("─" * 60)
print(f"{'TOTAL':<26}{total_pp:<12}{total_sp}")
print()

# ---- FIND DISCREPANCIES ----

bad_days = [i for i in range(7) if pp_counts.get(i) is not None and pp_counts[i] != sp_counts[i]]

if not bad_days:
    print("✓ All counts match!")
    print("Done.")
    exit()

print("⚠  DISCREPANCIES FOUND:")
for i in bad_days:
    diff      = sp_counts[i] - pp_counts[i]
    direction = f"SP EXTRA {diff}" if diff > 0 else f"PP EXTRA {abs(diff)}"
    print(f"   {day_names[i]} ({week_dates[i].strftime('%m/%d')}): {direction}  [PP={pp_counts[i]} vs SP={sp_counts[i]}]")

print()
do_analysis = input("Run deep analysis on discrepancy days? (y/n): ").strip().lower()
if do_analysis != 'y':
    print("Done.")
    exit()

# ---- DEEP ANALYSIS PER BAD DAY ----

for i in bad_days:
    date     = week_dates[i]
    day_name = day_names[i]

    print()
    print("=" * 60)
    print(f"  DEEP ANALYSIS — {day_name}  {date.strftime('%m/%d/%Y')}")
    print("=" * 60)

    day_df = df[df['Alert Date'].dt.date == date.date()].copy()
    day_df['_session_num'] = day_df['Session ID'].apply(get_session_num)
    day_df = day_df.sort_values('_session_num')

    print(f"  SP records for this day: {len(day_df)}")

    # Next business day
    next_biz = date + timedelta(days=1)
    while next_biz.weekday() >= 5:
        next_biz += timedelta(days=1)

    # ── CHECK 1: Session ID Sequence Anomaly ──────────────────
    print()
    print("  [1] Session ID Sequence Check")

    if len(day_df) >= 2:
        min_id = day_df['_session_num'].min()
        max_id = day_df['_session_num'].max()

        gap_df = df[
            (df['Session ID'].apply(get_session_num) > min_id) &
            (df['Session ID'].apply(get_session_num) < max_id) &
            (df['Alert Date'].dt.date != date.date())
        ]

        if len(gap_df) > 0:
            print(f"  ⚠ {len(gap_df)} record(s) inside this day's Session ID range but different Alert Date:")
            for _, r in gap_df.iterrows():
                print(f"    {r['Session ID']}  →  Alert Date: {r['Alert Date']}")
        else:
            print("  ✓ No sequence anomalies")
    else:
        print("  (Not enough records to check sequence)")

    # ── CHECK 2: Timeline Violations ─────────────────────────
    print()
    print("  [2] Timeline Violations")
    print("  (Note: Alert→Action being next day is NORMAL and not flagged)")

    tl_issues = []
    for _, r in day_df.iterrows():
        sid  = r['Session ID']
        ad   = pd.to_datetime(r['Alert Date'],                        errors='coerce')
        act  = pd.to_datetime(r.get('Action Date',              np.nan), errors='coerce')
        comp = pd.to_datetime(r.get('AnalysisCompletionDate',   np.nan), errors='coerce')
        pr_s = pd.to_datetime(r.get('Peer_Review_Start',        np.nan), errors='coerce')
        pr_e = pd.to_datetime(r.get('Peer_Review_End',          np.nan), errors='coerce')

        # Impossible: Action before Alert
        if pd.notna(act) and pd.notna(ad) and act.date() < ad.date():
            tl_issues.append(f"{sid} : Action Date ({r.get('Action Date')}) BEFORE Alert Date ({r['Alert Date']}) ← impossible")

        # Impossible: Completion before Action
        if pd.notna(comp) and pd.notna(act) and comp.date() < act.date():
            tl_issues.append(f"{sid} : Completion ({r.get('AnalysisCompletionDate')}) BEFORE Action Date ({r.get('Action Date')}) ← impossible")

        # Impossible: Peer Review End before Start
        if pd.notna(pr_e) and pd.notna(pr_s) and pr_e.date() < pr_s.date():
            tl_issues.append(f"{sid} : Peer Review End ({r.get('Peer_Review_End')}) BEFORE Start ({r.get('Peer_Review_Start')}) ← impossible")

        # Unusually long: >5 biz days
        if pd.notna(comp) and pd.notna(ad):
            biz = get_biz_day_diff(ad, comp)
            if biz > 5:
                tl_issues.append(f"{sid} : Alert→Completion = {biz} biz days ({r['Alert Date']} → {r.get('AnalysisCompletionDate')}) ← unusually long")

    if tl_issues:
        print("  ⚠ Issues found:")
        for issue in tl_issues:
            print(f"    {issue}")
    else:
        print("  ✓ No timeline violations")

    # ── CHECK 3: Empty / Suspicious Fields ───────────────────
    print()
    print("  [3] Empty / Suspicious Fields")

    crit_fields = ['Alert Rule','Status','ACF2ID','Analyst Name','Sign-off status']
    fld_issues  = []

    for _, r in day_df.iterrows():
        for f in crit_fields:
            if f in df.columns and is_suspicious(r.get(f, np.nan)):
                fld_issues.append(f"{r['Session ID']} : '{f}' empty/suspicious  →  '{r.get(f, '')}'")

    if fld_issues:
        print("  ⚠ Issues found:")
        for issue in fld_issues:
            print(f"    {issue}")
    else:
        print("  ✓ All critical fields look populated")

    # ── CHECK 4: Adjacent Day Bleed ───────────────────────────
    print()
    print(f"  [4] Adjacent Day Bleed Check  ({date.strftime('%m/%d')} ↔ {next_biz.strftime('%m/%d')})")

    next_df = df[df['Alert Date'].dt.date == next_biz.date()].copy()
    next_df['_session_num'] = next_df['Session ID'].apply(get_session_num)

    if len(day_df) > 0 and len(next_df) > 0:
        day_max = day_df['_session_num'].max()
        nxt_min = next_df['_session_num'].min()

        if nxt_min <= day_max:
            print(f"  ⚠ Session ID overlap — possible bleed between days:")
            print(f"    {day_name} max Session ID : {day_max}")
            print(f"    {next_biz.strftime('%m/%d')} min Session ID : {nxt_min}")
        else:
            print("  ✓ Session IDs cleanly separated between days")
    else:
        print("  (Not enough data on one or both days to compare)")

    # ── SUGGESTED ACTION ─────────────────────────────────────
    print()
    print("  ► Suggested Action:")
    print(f"    1. Filter SP by Alert Date = {date.strftime('%m/%d/%Y')}")
    print(f"    2. Also check {next_biz.strftime('%m/%d/%Y')} for any bleed-over alerts")
    print(f"    3. Review flagged Session IDs above manually")

print()
print("Done.")
