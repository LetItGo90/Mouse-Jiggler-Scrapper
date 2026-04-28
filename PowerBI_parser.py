#!/usr/bin/env python3
"""
ObserveIT / SharePoint Ticket Validation Script
Compares manually-created SharePoint tickets against ProofPoint ObserveIT alert export.
Focuses on date entry errors — wrong alert dates, impossible date ordering, and count mismatches.

Usage:
    python validate_tickets.py alerts_export.csv observeit_export.csv --week-start 2026-04-20
    python validate_tickets.py alerts_export.csv observeit_export.csv --week-start 2026-04-20 --output report.xlsx
"""

import pandas as pd
import sys
from datetime import datetime, timedelta, time
from collections import defaultdict
import argparse
import os
import re

# ──────────────────────────────────────────────────────────
# COLUMN MAPPINGS — adjust if your headers vary
# ──────────────────────────────────────────────────────────

# SharePoint (alerts_export.csv)
SP_SESSION_ID    = "Session ID"
SP_ALERT_DATE    = "Alert Date"
SP_CREATED       = "Created"
SP_CREATED_BY    = "Created By"
SP_STATUS        = "Status"
SP_ALERT_RULE    = "Alert Rule"
SP_SEVERITY      = "Severity"
SP_ACTION_DATE   = "Action Date"
SP_ANALYST       = "Analyst Name"
SP_COMMENTS      = "Comments"
SP_ACF2ID        = "ACF2iD"
SP_ANALYSIS_DONE = "AnalysisCompletionDate"
SP_ALLEGATION    = "Original_Allegation"
SP_PEER_START    = "Peer_Review_Start"
SP_PEER_END      = "Peer_Review_End"
SP_SIGNOFF       = "Sign-off status"

# ObserveIT / ProofPoint export
OI_RISK_LEVEL    = "Risk Level"
OI_ALERT_RULE    = "Alert Rule Name"
OI_USER_ID       = "User Identity"
OI_ALERT_DATE    = "Alert Date"
OI_APP           = "Interacted Application"
OI_ENDPOINT      = "Endpoint Name"
OI_ALERT_DETAIL  = "Alert Detail"


# ──────────────────────────────────────────────────────────

def load_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext in [".xlsx", ".xls"]:
        return pd.read_excel(filepath)
    for enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
        try:
            return pd.read_csv(filepath, encoding=enc)
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    return pd.read_csv(filepath, encoding="latin-1", on_bad_lines="skip")


def parse_dt(series, col_name="column"):
    parsed = pd.to_datetime(series, errors="coerce", infer_datetime_format=True)
    bad = parsed.isna() & series.notna() & (series.astype(str).str.strip() != "")
    if bad.any():
        examples = series[bad].unique()[:5]
        print(f"  ⚠  Could not parse {bad.sum()} value(s) in '{col_name}': {list(examples)}")
    return parsed


def hdr(title):
    w = 72
    print(f"\n{'=' * w}\n  {title}\n{'=' * w}")


def sub(title):
    print(f"\n  ── {title} {'─' * max(1, 58 - len(title))}")


def main():
    parser = argparse.ArgumentParser(description="Validate SP tickets vs ObserveIT alerts.")
    parser.add_argument("sharepoint_file", help="SharePoint export (alerts_export.csv)")
    parser.add_argument("observeit_file", help="ObserveIT export (CSV or Excel)")
    parser.add_argument("--week-start", required=True, help="Monday of reporting week: YYYY-MM-DD")
    parser.add_argument("--output", default=None, help="Optional Excel report output path")
    args = parser.parse_args()

    week_start = datetime.strptime(args.week_start, "%Y-%m-%d").date()
    week_end = week_start + timedelta(days=6)
    weekdays = [week_start + timedelta(days=i) for i in range(7)]

    # ══════════════════════════════════════════════════════
    # LOAD
    # ══════════════════════════════════════════════════════
    hdr("LOADING DATA")
    sp = load_file(args.sharepoint_file)
    oi = load_file(args.observeit_file)
    print(f"  SharePoint: {len(sp)} rows   Columns: {list(sp.columns)}")
    print(f"  ObserveIT:  {len(oi)} rows   Columns: {list(oi.columns)}")

    # ══════════════════════════════════════════════════════
    # PARSE DATES
    # ══════════════════════════════════════════════════════
    hdr("PARSING DATES")

    sp["_alert_dt"]    = parse_dt(sp[SP_ALERT_DATE],    "SP Alert Date")
    sp["_created_dt"]  = parse_dt(sp[SP_CREATED],       "SP Created")
    sp["_action_dt"]   = parse_dt(sp[SP_ACTION_DATE],   "SP Action Date")
    sp["_analysis_dt"] = parse_dt(sp[SP_ANALYSIS_DONE], "SP AnalysisCompletionDate")

    sp["_alert_date"]  = sp["_alert_dt"].dt.date
    sp["_user"]        = sp[SP_ACF2ID].astype(str).str.strip().str.lower()

    oi["_alert_dt"]    = parse_dt(oi[OI_ALERT_DATE], "OI Alert Date")
    oi["_alert_date"]  = oi["_alert_dt"].dt.date
    oi["_user"]        = oi[OI_USER_ID].astype(str).str.strip().str.lower()

    # Filter OI to reporting week
    oi_week = oi[(oi["_alert_date"] >= week_start) & (oi["_alert_date"] <= week_end)].copy()

    print(f"\n  Reporting week: {week_start} (Mon) → {week_end} (Sun)")
    print(f"  ObserveIT filtered to week: {len(oi_week)}  (full export: {len(oi)})")
    print(f"  SharePoint tickets:         {len(sp)}")

    # Collection for Excel output
    excel_sheets = {}

    # ══════════════════════════════════════════════════════
    # CHECK 1: INTERNAL DATE LOGIC
    # Alert Date ≤ Created ≤ Action Date ≤ AnalysisCompletion
    # ══════════════════════════════════════════════════════
    hdr("CHECK 1 — IMPOSSIBLE DATE ORDERING")

    rules = [
        ("_action_dt",   "_alert_dt",    "Action Date BEFORE Alert Date"),
        ("_created_dt",  "_alert_dt",    "Created BEFORE Alert Date"),
        ("_analysis_dt", "_created_dt",  "AnalysisCompletion BEFORE Created"),
        ("_analysis_dt", "_action_dt",   "AnalysisCompletion BEFORE Action Date"),
        ("_action_dt",   "_created_dt",  "Action Date BEFORE Created"),
    ]

    date_issues = []
    for idx, row in sp.iterrows():
        problems = []
        for early_col, late_col, label in rules:
            # The field that should be LATER is early_col
            # The field that should be EARLIER is late_col
            # So if late_col > early_col, that's wrong
            # Wait, let me re-read: "Action Date BEFORE Alert Date" means action_dt < alert_dt
            # So we check: early_col < late_col means early_col happened before late_col
            # "Action Date BEFORE Alert Date" = action_dt < alert_dt → impossible
            val_a = row[early_col]  # the one that should NOT be before
            val_b = row[late_col]   # the one that should come first
            if pd.notna(val_a) and pd.notna(val_b) and val_a < val_b:
                problems.append(label)

        if problems:
            date_issues.append({
                "Session ID": row[SP_SESSION_ID],
                "Alert Date": row[SP_ALERT_DATE],
                "Created": row[SP_CREATED],
                "Action Date": row[SP_ACTION_DATE],
                "AnalysisCompletion": row[SP_ANALYSIS_DONE],
                "Problems": " | ".join(problems)
            })

    if not date_issues:
        print("  ✅ All tickets have valid date ordering.")
    else:
        print(f"  ❌ {len(date_issues)} ticket(s) with impossible date ordering:\n")
        for item in date_issues[:25]:
            print(f"     SID {item['Session ID']}")
            print(f"       Alert={item['Alert Date']}  Created={item['Created']}")
            print(f"       Action={item['Action Date']}  Analysis={item['AnalysisCompletion']}")
            print(f"       → {item['Problems']}")
            print()
        if len(date_issues) > 25:
            print(f"     ... and {len(date_issues) - 25} more (see Excel output)")

    date_issues_df = pd.DataFrame(date_issues)
    if len(date_issues_df) > 0:
        excel_sheets["Date Order Errors"] = date_issues_df

    # ══════════════════════════════════════════════════════
    # CHECK 2: ALERT DATES OUTSIDE REPORTING WEEK
    # ══════════════════════════════════════════════════════
    hdr("CHECK 2 — ALERT DATES OUTSIDE REPORTING WEEK")

    sp_outside = sp[
        sp["_alert_date"].apply(lambda d: (d < week_start or d > week_end) if pd.notna(d) else False)
    ]

    if len(sp_outside) == 0:
        print("  ✅ All tickets fall within the reporting week.")
    else:
        print(f"  ❌ {len(sp_outside)} ticket(s) outside {week_start} → {week_end}:\n")
        for _, row in sp_outside.iterrows():
            print(f"     SID {row[SP_SESSION_ID]}  |  Alert Date: {row[SP_ALERT_DATE]}  |  User: {row[SP_ACF2ID]}")
        excel_sheets["Outside Week"] = sp_outside[[SP_SESSION_ID, SP_ALERT_DATE, SP_ACF2ID, SP_ALERT_RULE]].copy()

    # ══════════════════════════════════════════════════════
    # CHECK 3: OVERALL COUNT
    # ══════════════════════════════════════════════════════
    hdr("CHECK 3 — OVERALL COUNT")

    sp_n = len(sp)
    oi_n = len(oi_week)
    diff = sp_n - oi_n

    print(f"  SharePoint:  {sp_n}")
    print(f"  ObserveIT:   {oi_n}")
    if diff == 0:
        print("  ✅ Match!")
    else:
        word = "MORE" if diff > 0 else "FEWER"
        print(f"  ❌ SharePoint has {abs(diff)} {word} than ObserveIT")

    # ══════════════════════════════════════════════════════
    # CHECK 4: DAILY COUNTS + SWAP DETECTION
    # ══════════════════════════════════════════════════════
    hdr("CHECK 4 — DAILY COUNTS (with swap detection)")

    sp_daily = sp.groupby("_alert_date").size()
    oi_daily = oi_week.groupby("_alert_date").size()

    daily_rows = []
    for d in weekdays:
        s = sp_daily.get(d, 0)
        o = oi_daily.get(d, 0)
        delta = s - o
        dn = d.strftime("%a")
        flag = "✅" if delta == 0 else "❌"
        sign = f"+{delta}" if delta > 0 else str(delta)
        extra = f"  (diff: {sign})" if delta != 0 else ""
        print(f"  {flag} {d} ({dn})  SP={s:4d}  OI={o:4d}{extra}")
        daily_rows.append({"Date": d, "Day": dn, "SP": s, "OI": o, "Diff": delta})

    daily_df = pd.DataFrame(daily_rows)
    excel_sheets["Daily Counts"] = daily_df

    # Swap detection: adjacent days where one is +N and the other is -N
    sub("Possible day swaps")
    swaps_found = False
    for i in range(len(daily_rows) - 1):
        d1 = daily_rows[i]
        d2 = daily_rows[i + 1]
        if d1["Diff"] != 0 and d2["Diff"] != 0:
            if d1["Diff"] == -d2["Diff"]:
                swaps_found = True
                print(f"  🔄 Likely swap: {d1['Date']} ({d1['Day']}) is {d1['Diff']:+d} "
                      f"and {d2['Date']} ({d2['Day']}) is {d2['Diff']:+d}")
                print(f"     → Probably {abs(d1['Diff'])} ticket(s) have the wrong day entered")
            elif abs(d1["Diff"] + d2["Diff"]) <= 1 and abs(d1["Diff"]) > 1:
                swaps_found = True
                print(f"  🔄 Probable partial swap: {d1['Date']} is {d1['Diff']:+d} "
                      f"and {d2['Date']} is {d2['Diff']:+d} (off by {abs(d1['Diff'] + d2['Diff'])})")

    if not swaps_found:
        # Check non-adjacent days too
        for i in range(len(daily_rows)):
            for j in range(i + 2, len(daily_rows)):
                d1 = daily_rows[i]
                d2 = daily_rows[j]
                if d1["Diff"] != 0 and d2["Diff"] != 0 and d1["Diff"] == -d2["Diff"]:
                    swaps_found = True
                    print(f"  🔄 Possible swap (non-adjacent): {d1['Date']} ({d1['Day']}) is {d1['Diff']:+d} "
                          f"and {d2['Date']} ({d2['Day']}) is {d2['Diff']:+d}")

    if not swaps_found:
        if diff == 0 and all(r["Diff"] == 0 for r in daily_rows):
            print("  ✅ No swaps — all days match perfectly.")
        elif any(r["Diff"] != 0 for r in daily_rows):
            print("  ⚠  Discrepancies found but no clean swap pattern — could be missing/extra tickets.")

    # ══════════════════════════════════════════════════════
    # CHECK 5: PER-USER DAILY COUNTS
    # Narrow down WHICH user's ticket has the wrong date
    # ══════════════════════════════════════════════════════
    hdr("CHECK 5 — PER-USER DAILY COUNTS (pinpoint wrong dates)")

    sp_user_day = sp.groupby(["_user", "_alert_date"]).size().reset_index(name="SP")
    oi_user_day = oi_week.groupby(["_user", "_alert_date"]).size().reset_index(name="OI")

    user_merged = pd.merge(sp_user_day, oi_user_day,
                           on=["_user", "_alert_date"], how="outer", indicator=True)
    user_merged["SP"] = user_merged["SP"].fillna(0).astype(int)
    user_merged["OI"] = user_merged["OI"].fillna(0).astype(int)
    user_merged["Diff"] = user_merged["SP"] - user_merged["OI"]

    user_mismatches = user_merged[user_merged["Diff"] != 0].sort_values(["_user", "_alert_date"])

    # Group by user to show the pattern
    if len(user_mismatches) == 0:
        print("  ✅ Every (user, date) combination matches between systems!")
    else:
        problem_users = user_mismatches["_user"].unique()
        print(f"  ❌ {len(problem_users)} user(s) have date count mismatches:\n")

        for user in problem_users[:20]:
            user_rows = user_mismatches[user_mismatches["_user"] == user]
            print(f"  👤 {user}:")
            for _, r in user_rows.iterrows():
                d = r["_alert_date"]
                day_name = d.strftime("%a") if pd.notna(d) else "?"
                print(f"       {d} ({day_name})  SP={r['SP']}  OI={r['OI']}  (diff: {r['Diff']:+d})")

            # Check for user-level swap pattern
            user_all = user_rows.to_dict("records")
            for a in range(len(user_all)):
                for b in range(a + 1, len(user_all)):
                    if user_all[a]["Diff"] == -user_all[b]["Diff"] and user_all[a]["Diff"] != 0:
                        print(f"       🔄 Swap: {abs(user_all[a]['Diff'])} alert(s) likely dated "
                              f"{user_all[a]['_alert_date']} instead of {user_all[b]['_alert_date']} "
                              f"(or vice versa)")
            print()

        if len(problem_users) > 20:
            print(f"  ... and {len(problem_users) - 20} more users (see Excel output)")

        excel_sheets["User Date Mismatches"] = user_mismatches.copy()

    # ══════════════════════════════════════════════════════
    # CHECK 6: SESSION ID SEQUENCE ANALYSIS
    # ══════════════════════════════════════════════════════
    hdr("CHECK 6 — SESSION ID SEQUENCE ANALYSIS")

    sp_seq = sp.copy()
    sp_seq["_sid_num"] = pd.to_numeric(sp_seq[SP_SESSION_ID], errors="coerce")
    sp_seq = sp_seq.dropna(subset=["_sid_num", "_alert_date"])
    sp_seq = sp_seq.sort_values("_sid_num").reset_index(drop=True)

    seq_issues = []
    if len(sp_seq) >= 3:
        for i in range(1, len(sp_seq) - 1):
            p = sp_seq.iloc[i - 1]
            c = sp_seq.iloc[i]
            n = sp_seq.iloc[i + 1]

            # Only check if SIDs are reasonably close (same batch)
            if (c["_sid_num"] - p["_sid_num"]) > 10 or (n["_sid_num"] - c["_sid_num"]) > 10:
                continue

            # Neighbors same date, current different
            if p["_alert_date"] == n["_alert_date"] and c["_alert_date"] != p["_alert_date"]:
                seq_issues.append({
                    "Session ID": int(c["_sid_num"]),
                    "Entered Date": str(c["_alert_date"]),
                    "Expected Date": str(p["_alert_date"]),
                    "Prev SID": int(p["_sid_num"]),
                    "Next SID": int(n["_sid_num"]),
                    "User": c.get(SP_ACF2ID, ""),
                    "Rule": c.get(SP_ALERT_RULE, "")
                })

    if not seq_issues:
        print("  ✅ No date breaks found in Session ID sequences.")
    else:
        print(f"  ❌ {len(seq_issues)} ticket(s) break the date sequence:\n")
        for s in seq_issues[:20]:
            print(f"     SID {s['Session ID']}:  entered {s['Entered Date']}, "
                  f"but neighbors ({s['Prev SID']}, {s['Next SID']}) are both {s['Expected Date']}")
            print(f"       User: {s['User']}  Rule: {s['Rule']}")
        if len(seq_issues) > 20:
            print(f"     ... and {len(seq_issues) - 20} more")

        seq_df = pd.DataFrame(seq_issues)
        excel_sheets["Sequence Breaks"] = seq_df

    # ══════════════════════════════════════════════════════
    # CHECK 7: DUPLICATE SESSION IDs
    # ══════════════════════════════════════════════════════
    hdr("CHECK 7 — DUPLICATE SESSION IDs")

    dupes = sp[sp.duplicated(subset=[SP_SESSION_ID], keep=False)]
    if len(dupes) == 0:
        print("  ✅ No duplicates.")
    else:
        dup_groups = dupes.groupby(SP_SESSION_ID).size()
        print(f"  ❌ {len(dup_groups)} duplicated Session ID(s):\n")
        for sid, cnt in dup_groups.items():
            rows = dupes[dupes[SP_SESSION_ID] == sid]
            dates = rows[SP_ALERT_DATE].tolist()
            print(f"     SID {sid} × {cnt}  dates: {dates}")
        excel_sheets["Duplicates"] = dupes[[SP_SESSION_ID, SP_ALERT_DATE, SP_ACF2ID, SP_ALERT_RULE]].copy()

    # ══════════════════════════════════════════════════════
    # CHECK 8: ALERT DATE vs CREATED DATE GAP
    # If someone makes a ticket 3+ days after the alert, flag it
    # (could mean they used the wrong week's alert)
    # ══════════════════════════════════════════════════════
    hdr("CHECK 8 — LARGE GAP BETWEEN ALERT DATE AND CREATED DATE")

    sp["_gap_days"] = (sp["_created_dt"] - sp["_alert_dt"]).dt.total_seconds() / 86400

    big_gap = sp[sp["_gap_days"].abs() > 3].copy()
    if len(big_gap) == 0:
        print("  ✅ All tickets created within 3 days of alert date.")
    else:
        print(f"  ⚠  {len(big_gap)} ticket(s) with >3 day gap between Alert Date and Created:\n")
        for _, row in big_gap.head(15).iterrows():
            gap = row["_gap_days"]
            direction = "after" if gap > 0 else "BEFORE"
            print(f"     SID {row[SP_SESSION_ID]}  Alert: {row[SP_ALERT_DATE]}  "
                  f"Created: {row[SP_CREATED]}  ({abs(gap):.1f} days {direction})")
        if len(big_gap) > 15:
            print(f"     ... and {len(big_gap) - 15} more")
        excel_sheets["Large Date Gaps"] = big_gap[[SP_SESSION_ID, SP_ALERT_DATE, SP_CREATED, "_gap_days"]].copy()

    # ══════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════
    hdr("SUMMARY")

    n_dup = len(dupes.groupby(SP_SESSION_ID)) if len(dupes) > 0 else 0
    n_swaps = sum(1 for r in daily_rows if r["Diff"] != 0)

    print(f"  Date ordering errors:                {len(date_issues)}")
    print(f"  Tickets outside reporting week:       {len(sp_outside)}")
    print(f"  Overall count discrepancy (SP-OI):    {diff:+d}")
    print(f"  Days with count mismatches:           {n_swaps} / 7")
    print(f"  Users with date mismatches:           {len(user_mismatches['_user'].unique()) if len(user_mismatches) > 0 else 0}")
    print(f"  Session ID sequence breaks:           {len(seq_issues)}")
    print(f"  Duplicate Session IDs:                {n_dup}")
    print(f"  Large alert-to-created gaps:          {len(big_gap)}")

    total = len(date_issues) + len(sp_outside) + len(seq_issues) + n_dup + len(big_gap)
    if total == 0 and diff == 0:
        print("\n  🎉 No issues found! Clean week.")
    else:
        print(f"\n  ⚠  {total} issue(s) flagged — review above for details.")
    print()

    # ══════════════════════════════════════════════════════
    # EXCEL OUTPUT
    # ══════════════════════════════════════════════════════
    if args.output:
        print(f"  Writing report to: {args.output}")
        with pd.ExcelWriter(args.output, engine="openpyxl") as writer:
            for sheet_name, df in excel_sheets.items():
                df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
        print("  ✅ Done.\n")


if __name__ == "__main__":
    main()
