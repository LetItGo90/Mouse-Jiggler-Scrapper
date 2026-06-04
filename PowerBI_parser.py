import os
import pandas as pd
import matplotlib.pyplot as plt
from fpdf import FPDF
from datetime import datetime, timedelta

# ---------- CONFIG ----------
CSV_FILE = "alerts.csv"
CHART_DIR = "charts"
TODAY = datetime.today()
REPORT_DATE = TODAY.strftime("%Y-%m-%d")
PDF_FILE = f"Weekly_Report_{REPORT_DATE}.pdf"

# Adjust these column names if your CSV uses different headers
COL_STATUS    = "Status"
COL_ANALYST   = "Analyst"
COL_ALERTTYPE = "AlertType"     # or "Rule" / "AlertName"
COL_SEVERITY  = "Severity"
COL_DATE      = "CreatedDate"   # date alert was generated

COMPLETED_STATUSES = ["Non-Issue", "Issue"]
OPEN_STATUSES      = ["Reviewing"]

os.makedirs(CHART_DIR, exist_ok=True)

# ---------- LOAD ----------
df = pd.read_csv(CSV_FILE)
df[COL_DATE] = pd.to_datetime(df[COL_DATE], errors="coerce")

cutoff_90 = TODAY - timedelta(days=90)
cutoff_7  = TODAY - timedelta(days=7)

df_90 = df[df[COL_DATE] >= cutoff_90].copy()
df_7  = df[df[COL_DATE] >= cutoff_7].copy()

# ---------- CHART 1: Weekly volume trend (90d) ----------
weekly = df_90.groupby(pd.Grouper(key=COL_DATE, freq="W")).size()
plt.figure(figsize=(10, 4))
plt.plot(weekly.index, weekly.values, marker="o", color="#2E7D32", linewidth=2)
plt.title("Alert Volume Trend - Last 90 Days (Weekly)")
plt.xlabel("Week Ending"); plt.ylabel("Alert Count")
plt.grid(True, alpha=0.3); plt.tight_layout()
plt.savefig(f"{CHART_DIR}/trend_volume.png", dpi=120); plt.close()

# ---------- CHART 2: Trend by alert type (90d) ----------
if COL_ALERTTYPE in df_90.columns:
    by_type = (df_90.groupby([pd.Grouper(key=COL_DATE, freq="W"), COL_ALERTTYPE])
                    .size().unstack(fill_value=0))
    by_type.plot(figsize=(10, 5), marker="o")
    plt.title("Alert Type Trend - Last 90 Days")
    plt.xlabel("Week Ending"); plt.ylabel("Count")
    plt.legend(loc="upper left", fontsize=7, ncol=2)
    plt.grid(True, alpha=0.3); plt.tight_layout()
    plt.savefig(f"{CHART_DIR}/trend_by_type.png", dpi=120); plt.close()

# ---------- CHART 3: Severity breakdown (last 7d) ----------
if COL_SEVERITY in df_7.columns:
    sev = df_7[COL_SEVERITY].value_counts()
    plt.figure(figsize=(6, 4))
    sev.plot(kind="bar", color="#2E7D32", edgecolor="black")
    plt.title("Alerts by Severity - Last 7 Days")
    plt.ylabel("Count"); plt.xticks(rotation=0)
    plt.tight_layout()
    plt.savefig(f"{CHART_DIR}/severity.png", dpi=120); plt.close()

# ---------- CHART 4: Analyst completions (90d) ----------
# Counts alerts where status is Non-Issue or Issue (i.e. dispositioned)
completed_90 = df_90[df_90[COL_STATUS].isin(COMPLETED_STATUSES)]
analyst_counts = completed_90[COL_ANALYST].value_counts()
plt.figure(figsize=(10, 5))
analyst_counts.plot(kind="bar", color="#2E7D32", edgecolor="black")
plt.title("Alerts Completed by Analyst - Last 90 Days")
plt.xlabel("Analyst"); plt.ylabel("Completed Alerts (Issue + Non-Issue)")
plt.xticks(rotation=30, ha="right")
plt.tight_layout()
plt.savefig(f"{CHART_DIR}/analyst.png", dpi=120); plt.close()

# ---------- CHART 5: Open alerts aging (Reviewing) ----------
open_alerts = df[df[COL_STATUS].isin(OPEN_STATUSES)].copy()
open_alerts["AgeDays"] = (TODAY - open_alerts[COL_DATE]).dt.days
bins   = [0, 7, 14, 30, 60, 9999]
labels = ["0-7d", "8-14d", "15-30d", "31-60d", "60d+"]
open_alerts["AgeBucket"] = pd.cut(open_alerts["AgeDays"], bins=bins, labels=labels)
aging = open_alerts["AgeBucket"].value_counts().reindex(labels, fill_value=0)
plt.figure(figsize=(8, 4))
aging.plot(kind="bar", color="#C62828", edgecolor="black")
plt.title("Open Alerts (Reviewing) - Aging Buckets")
plt.ylabel("Count"); plt.xticks(rotation=0)
plt.tight_layout()
plt.savefig(f"{CHART_DIR}/aging.png", dpi=120); plt.close()

# ---------- WEEK-OVER-WEEK STATS ----------
this_week = df[(df[COL_DATE] >= cutoff_7)].shape[0]
last_week = df[(df[COL_DATE] >= cutoff_7 - timedelta(days=7)) &
               (df[COL_DATE] <  cutoff_7)].shape[0]
wow_delta = this_week - last_week
wow_pct   = (wow_delta / last_week * 100) if last_week else 0

# ---------- PDF BUILD ----------
class PDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, "Insider Enhanced Surveillance - Weekly Report", ln=True, align="C")
        self.set_font("Helvetica", "", 10)
        self.cell(0, 6, f"Report Date: {REPORT_DATE}", ln=True, align="C")
        self.ln(4)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")

    def section(self, title):
        self.set_font("Helvetica", "B", 12)
        self.set_fill_color(230, 230, 230)
        self.cell(0, 8, title, ln=True, fill=True)
        self.ln(2)

    def body(self, text):
        self.set_font("Helvetica", "", 10)
        self.multi_cell(0, 5, text)
        self.ln(2)

pdf = PDF()
pdf.add_page()

# Executive summary
pdf.section("Executive Summary")
pdf.body(
    f"Total alerts last 7 days: {this_week}\n"
    f"Total alerts prior 7 days: {last_week}\n"
    f"Week-over-week change: {wow_delta:+d} ({wow_pct:+.1f}%)\n"
    f"Open alerts (Reviewing): {open_alerts.shape[0]}\n"
    f"  - Aged >30 days: {int(aging.get('31-60d', 0) + aging.get('60d+', 0))}\n"
    f"Completed last 90 days: {completed_90.shape[0]} "
    f"(Issue: {(completed_90[COL_STATUS]=='Issue').sum()}, "
    f"Non-Issue: {(completed_90[COL_STATUS]=='Non-Issue').sum()})"
)

# 90-day trends
pdf.section("90-Day Volume Trend")
pdf.image(f"{CHART_DIR}/trend_volume.png", w=180)

if os.path.exists(f"{CHART_DIR}/trend_by_type.png"):
    pdf.add_page()
    pdf.section("90-Day Trend by Alert Type")
    pdf.image(f"{CHART_DIR}/trend_by_type.png", w=180)

# Severity
if os.path.exists(f"{CHART_DIR}/severity.png"):
    pdf.add_page()
    pdf.section("Severity Breakdown - Last 7 Days")
    pdf.image(f"{CHART_DIR}/severity.png", w=140)

# Analyst
pdf.add_page()
pdf.section("Analyst Productivity - Last 90 Days")
pdf.image(f"{CHART_DIR}/analyst.png", w=180)

# Aging
pdf.section("Open Alert Aging")
pdf.image(f"{CHART_DIR}/aging.png", w=160)

pdf.output(PDF_FILE)
print(f"Report generated: {PDF_FILE}")



python -c "import pandas as pd; print(pd.read_csv('alerts.csv').columns.tolist())"
