# alert_check.py
import pandas as pd
import sys
from datetime import datetime

# ============================================================
# COLUMN NAMES - update these to match your SharePoint export
# ============================================================
COL_SESSION_ID = "Session ID"
COL_ALERT_DATE = "Alert Date"
COL_CREATED = "Created"
COL_CREATED_BY = "Created By"
COL_STATUS = "Status"
COL_ALERT_RULE = "Alert Rule"
COL_SEVERITY = "Severity"
COL_ACTION_DATE = "Action Date"
COL_ANALYST = "Analyst Name"
COL_COMMENTS = "Comments"
COL_ACF2ID = "ACF2ID"
COL_ANALYSIS_COMP = "AnalysisCompletionDate"
COL_ALLEGATION = "Original_Allegation"

# Valid statuses
VALID_STATUSES = ["non-issue", "issue"]

DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def parse_date_col(series):
    """Try multiple date formats."""
    for fmt in ["%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M", "%m/%d/%Y",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", None]:
        try:
            if fmt:
                return pd.to_datetime(series, format=fmt, errors="raise")
            else:
                return pd.to_datetime(series, errors="coerce", dayfirst=False)
        except (ValueError, TypeError):
            continue
    return pd.to_datetime(series, errors="coerce")


def load_sharepoint(filepath):
    """Load and do basic cleanup on SharePoint CSV."""
    df = pd.read_csv(filepath, dtype=str)
    df.columns = df.columns.str.strip()
    print(f"\n  Loaded {len(df)} rows from SharePoint export")
    print(f"  Columns found: {df.columns.tolist()}")
    return df


def check_missing_fields(df):
    """Check for blank/missing required fields."""
    issues = []
    required = {
        COL_SESSION_ID: "Session ID",
        COL_ALERT_DATE: "Alert Date",
        COL_STATUS: "Status",
        COL_ANALYST: "Analyst Name",
        COL_ACF2ID: "ACF2ID",
        COL_COMMENTS: "Comments",
        COL_SEVERITY: "Severity",
        COL_ALERT_RULE: "Alert Rule",
    }

    print("\n[1] MISSING / BLANK FIELDS")
    found_any = False
    for col, label in required.items():
        if col not in df.columns:
            print(f"  ⚠️  Column '{col}' not found in export!")
            found_any = True
            continue
        blank = df[col].isna() | (df[col].str.strip() == "")
        count = blank.sum()
        if count > 0:
            found_any = True
            rows = df.index[blank].tolist()
            print(f"  ⚠️  {label}: {count} blank — rows {rows[:10]}{'...' if count > 10 else ''}")
            for idx in rows[:5]:
                sid = df.at[idx, COL_SESSION_ID] if COL_SESSION_ID in df.columns else "?"
                issues.append({
                    "Check": "Missing Field",
                    "Field": label,
                    "Row": idx,
                    "Session ID": sid,
                    "Detail": f"{label} is blank"
                })
    if not found_any:
        print("  ✅ All required fields populated")
    return issues


def check_duplicates(df):
    """Check for duplicate Session IDs."""
    print("\n[2] DUPLICATE SESSION IDs")
    issues = []
    if COL_SESSION_ID not in df.columns:
        print("  ⚠️  Session ID column not found, skipping")
        return issues

    dupes = df[df.duplicated(subset=[COL_SESSION_ID], keep=False)]
    if len(dupes) > 0:
        grouped = dupes.groupby(COL_SESSION_ID).size()
        print(f"  ⚠️  {len(grouped)} Session IDs appear more than once ({len(dupes)} total rows)")
        for sid, count in grouped.items():
            print(f"     • {sid} — {count} times")
            issues.append({
                "Check": "Duplicate",
                "Field": "Session ID",
                "Row": "",
                "Session ID": sid,
                "Detail": f"Appears {count} times"
            })
    else:
        print("  ✅ No duplicate Session IDs")
    return issues


def check_status(df):
    """Check for tickets not marked as Issue or Non-Issue."""
    print("\n[3] STATUS CHECK")
    issues = []
    if COL_STATUS not in df.columns:
        print("  ⚠️  Status column not found, skipping")
        return issues

    statuses = df[COL_STATUS].str.strip().str.lower()
    status_counts = df[COL_STATUS].value_counts()
    print("  Status breakdown:")
    for s, c in status_counts.items():
        print(f"     • {s}: {c}")

    invalid = ~statuses.isin(VALID_STATUSES)
    count = invalid.sum()
    if count > 0:
        print(f"\n  ⚠️  {count} ticket(s) with invalid status (expected 'Issue' or 'Non-Issue'):")
        for idx in df.index[invalid][:10]:
            sid = df.at[idx, COL_SESSION_ID] if COL_SESSION_ID in df.columns else "?"
            st = df.at[idx, COL_STATUS]
            print(f"     • Row {idx}, Session {sid}: status = '{st}'")
            issues.append({
                "Check": "Status",
                "Field": "Status",
                "Row": idx,
                "Session ID": sid,
                "Detail": f"Status is '{st}', expected Issue or Non-Issue"
            })
    else:
        print(f"\n  ✅ All tickets have valid status (Issue or Non-Issue)")

    return issues


def check_dates(df, week_start=None):
    """Check alert dates and work dates for issues."""
    print("\n[4] DATE CHECKS")
    issues = []
    if COL_ALERT_DATE not in df.columns:
        print("  ⚠️  Alert Date column not found, skipping")
        return issues

    dates = parse_date_col(df[COL_ALERT_DATE])

    # --- Unparseable dates ---
    bad_dates = dates.isna() & df[COL_ALERT_DATE].notna() & (df[COL_ALERT_DATE].str.strip() != "")
    if bad_dates.sum() > 0:
        print(f"  ⚠️  {bad_dates.sum()} rows have unparseable alert dates")
        for idx in df.index[bad_dates][:5]:
            print(f"     • Row {idx}: '{df.at[idx, COL_ALERT_DATE]}'")
            issues.append({
                "Check": "Bad Date",
                "Field": "Alert Date",
                "Row": idx,
                "Session ID": df.at[idx, COL_SESSION_ID] if COL_SESSION_ID in df.columns else "?",
                "Detail": f"Cannot parse '{df.at[idx, COL_ALERT_DATE]}'"
            })

    # --- Alert dates outside expected range ---
    # Alerts generate on weekends too, so valid range is Sat before Monday through Friday
    if week_start:
        ws = pd.Timestamp(week_start)
        range_start = ws - pd.Timedelta(days=2)  # Saturday before
        range_end = ws + pd.Timedelta(days=4, hours=23, minutes=59, seconds=59)  # Friday
        outside = dates.notna() & ((dates < range_start) | (dates > range_end))
        count = outside.sum()
        if count > 0:
            print(f"  ⚠️  {count} alert(s) fall outside the expected range "
                  f"({range_start.strftime('%m/%d')} Sat - {range_end.strftime('%m/%d')} Fri):")
            for idx in df.index[outside][:10]:
                sid = df.at[idx, COL_SESSION_ID] if COL_SESSION_ID in df.columns else "?"
                print(f"     • Row {idx}, Session {sid}: {dates[idx]}")
                issues.append({
                    "Check": "Out of Week",
                    "Field": "Alert Date",
                    "Row": idx,
                    "Session ID": sid,
                    "Detail": f"Date {dates[idx]} outside expected range"
                })
        else:
            print(f"  ✅ All alerts fall within expected range "
                  f"({range_start.strftime('%m/%d')} Sat - {range_end.strftime('%m/%d')} Fri)")

    # --- Work dates should NOT fall on weekends ---
    # Alerts generate on weekends but nobody works them on weekends.
    # Action Date / Analysis Completion Date on Sat/Sun = data entry error.
    work_date_cols = {
        COL_ACTION_DATE: "Action Date",
        COL_ANALYSIS_COMP: "Analysis Completion Date",
    }
    for col, label in work_date_cols.items():
        if col not in df.columns:
            continue
        work_dates = parse_date_col(df[col])
        weekend_mask = work_dates.notna() & work_dates.dt.dayofweek.isin([5, 6])
        wcount = weekend_mask.sum()
        if wcount > 0:
            print(f"  ⚠️  {wcount} row(s) have {label} on a WEEKEND (data entry error):")
            for idx in df.index[weekend_mask][:10]:
                sid = df.at[idx, COL_SESSION_ID] if COL_SESSION_ID in df.columns else "?"
                day_name = work_dates[idx].strftime('%A %m/%d/%Y')
                print(f"     • Row {idx}, Session {sid}: {label} = {day_name}")
                issues.append({
                    "Check": "Weekend Work Date",
                    "Field": label,
                    "Row": idx,
                    "Session ID": sid,
                    "Detail": f"{label} is {day_name} — weekend entry error"
                })
        else:
            print(f"  ✅ No {label} entries on weekends")

    # --- Action Date should be >= Alert Date ---
    if COL_ACTION_DATE in df.columns:
        action_dates = parse_date_col(df[COL_ACTION_DATE])
        backwards = dates.notna() & action_dates.notna() & (action_dates < dates)
        if backwards.sum() > 0:
            print(f"  ⚠️  {backwards.sum()} row(s) where Action Date is BEFORE Alert Date")
            for idx in df.index[backwards][:5]:
                sid = df.at[idx, COL_SESSION_ID] if COL_SESSION_ID in df.columns else "?"
                issues.append({
                    "Check": "Date Order",
                    "Field": "Action Date",
                    "Row": idx,
                    "Session ID": sid,
                    "Detail": f"Action {action_dates[idx]} before Alert {dates[idx]}"
                })
        else:
            print(f"  ✅ All Action Dates are on or after Alert Dates")

    return issues


def get_sp_daily_counts(df):
    """Get daily alert counts from SharePoint data.
    Weekend alerts (Sat/Sun) roll into Monday since that's when they're worked."""
    if COL_ALERT_DATE not in df.columns:
        return {}
    dates = parse_date_col(df[COL_ALERT_DATE])
    days = dates.dt.day_name()
    counts = {}
    for d in DAY_ORDER:
        counts[d] = (days == d).sum()
    # Roll weekend into Monday
    sat_count = (days == "Saturday").sum()
    sun_count = (days == "Sunday").sum()
    counts["Monday"] = counts.get("Monday", 0) + sat_count + sun_count
    return counts


def get_observeit_input():
    """Manually input ObserveIT numbers."""
    print("\n>>> OBSERVEIT MANUAL INPUT <<<")
    total = int(input("  Total ObserveIT alerts for the week: "))
    counts = {}
    for day in DAY_ORDER:
        while True:
            try:
                val = int(input(f"  {day}: "))
                counts[day] = val
                break
            except ValueError:
                print("  Enter a number.")
    return total, counts


def compare_counts(sp_daily, sp_total, oi_daily, oi_total):
    """Compare SharePoint vs ObserveIT counts."""
    issues = []
    print("\n[5] SHAREPOINT vs OBSERVEIT COMPARISON")

    # Totals
    print(f"\n  SharePoint total: {sp_total}  |  ObserveIT total: {oi_total}")
    diff = sp_total - oi_total
    if diff == 0:
        print(f"  ✅ Totals match")
    else:
        print(f"  ⚠️  Difference: {diff}")
        if diff > 0:
            print(f"     → SharePoint has {abs(diff)} MORE (possible duplicates in SP?)")
        else:
            print(f"     → ObserveIT has {abs(diff)} MORE (possible missing tickets in SP?)")
        issues.append({
            "Check": "Total Mismatch",
            "Field": "Count",
            "Row": "",
            "Session ID": "",
            "Detail": f"SP={sp_total} vs OI={oi_total}, diff={diff}"
        })

    # Daily breakdown — for troubleshooting where the gap is
    print(f"\n  {'Day':<12} {'SharePoint':>12} {'ObserveIT':>12} {'Diff':>8}  Status")
    print(f"  {'-'*12} {'-'*12} {'-'*12} {'-'*8}  {'-'*10}")

    for day in DAY_ORDER:
        sp_val = sp_daily.get(day, 0)
        oi_val = oi_daily.get(day, 0)
        d = sp_val - oi_val
        status = "✅" if d == 0 else "⚠️  MISMATCH"
        label = f"{day}*" if day == "Monday" else day
        print(f"  {label:<12} {sp_val:>12} {oi_val:>12} {d:>+8}  {status}")
        if d != 0:
            direction = "more in SP" if d > 0 else "more in OI"
            issues.append({
                "Check": "Daily Mismatch",
                "Field": day,
                "Row": "",
                "Session ID": "",
                "Detail": f"SP={sp_val} OI={oi_val} ({abs(d)} {direction})"
            })

    print(f"\n  * Monday includes weekend alerts (Sat/Sun)")

    return issues


def main():
    print("=" * 55)
    print("  WEEKLY ALERT QA CHECK")
    print("=" * 55)

    # --- Get SharePoint file ---
    if len(sys.argv) > 1:
        sp_file = sys.argv[1]
    else:
        sp_file = input("\nSharePoint CSV file path: ").strip().strip('"')

    # --- Optional week start ---
    week_start = None
    ws_input = input("Week start date (Monday, YYYY-MM-DD) or press Enter to skip: ").strip()
    if ws_input:
        week_start = ws_input

    # --- Load and check SharePoint ---
    df = load_sharepoint(sp_file)

    all_issues = []
    all_issues += check_missing_fields(df)
    all_issues += check_duplicates(df)
    all_issues += check_status(df)
    all_issues += check_dates(df, week_start)

    # --- SharePoint daily counts ---
    sp_daily = get_sp_daily_counts(df)
    sp_total = len(df)

    print(f"\n  SharePoint daily counts (weekend alerts rolled into Monday):")
    for day in DAY_ORDER:
        print(f"     {day}: {sp_daily.get(day, 0)}")
    daily_sum = sum(sp_daily.get(d, 0) for d in DAY_ORDER)
    if daily_sum != sp_total:
        print(f"  ⚠️  Daily sum = {daily_sum} but total rows = {sp_total} — check for unparsed dates")

    # --- ObserveIT comparison ---
    do_compare = input("\nCompare with ObserveIT? (y/n): ").strip().lower()
    if do_compare == "y":
        oi_total, oi_daily = get_observeit_input()
        all_issues += compare_counts(sp_daily, sp_total, oi_daily, oi_total)

    # --- FINAL SUMMARY ---
    print("\n" + "=" * 55)
    print("  FINAL SUMMARY")
    print("=" * 55)
    if not all_issues:
        print("\n  ✅ No issues found! Everything looks clean.")
    else:
        print(f"\n  Found {len(all_issues)} issue(s):\n")
        by_check = {}
        for iss in all_issues:
            by_check.setdefault(iss["Check"], []).append(iss)
        for check, items in by_check.items():
            print(f"  [{check}] — {len(items)} issue(s)")
            for item in items[:5]:
                print(f"     • {item['Detail']}")
            if len(items) > 5:
                print(f"     ... and {len(items)-5} more")

    # --- Optional export ---
    if all_issues:
        export = input("\nExport issues to CSV? (y/n): ").strip().lower()
        if export == "y":
            out = pd.DataFrame(all_issues)
            fname = "qa_issues.csv"
            out.to_csv(fname, index=False)
            print(f"  Saved to {fname}")

    print("\nDone!")


if __name__ == "__main__":
    main()
