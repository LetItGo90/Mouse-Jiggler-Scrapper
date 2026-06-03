import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from fpdf import FPDF
from pathlib import Path

# ---------- CONFIG ----------
CSV_PATH = "alerts.csv"
LOOKBACK_DAYS = 90
OUTPUT_PDF = f"Weekly_Report_{datetime.now().strftime('%Y-%m-%d')}.pdf"
CHART_DIR = Path("charts")
CHART_DIR.mkdir(exist_ok=True)

SEVERITY_ORDER = ["Critical", "High", "Medium", "Low", "Info"]
SEVERITY_COLORS = {
    "Critical": "#8B0000",
    "High":     "#E74C3C",
    "Medium":   "#F39C12",
    "Low":      "#3498DB",
    "Info":     "#95A5A6",
}
COMPLETED_STATUSES = ["Non-issue", "Issue"]   # everything not "Reviewing"
TRUE_POSITIVE_STATUS = "Issue"

PROGRAM_HIGHLIGHTS = """- Highlight 1 goes here
- Highlight 2 goes here
- Highlight 3 goes here"""

# ---------- LOAD ----------
df = pd.read_csv(CSV_PATH)
df.columns = [c.strip() for c in df.columns]

# Try common variations of the date column
date_col = next((c for c in df.columns if c.lower().replace(" ", "") == "alertdate"), None)
df["AlertDate"] = pd.to_datetime(df[date_col], errors="coerce")

# Standardize categorical columns
df["Severity"] = pd.Categorical(df["Severity"].str.strip(),
                                categories=SEVERITY_ORDER, ordered=True)
df["Status"] = df["Status"].str.strip()

cutoff = datetime.now() - timedelta(days=LOOKBACK_DAYS)
recent = df[df["AlertDate"] >= cutoff].copy()
recent["Week"] = recent["AlertDate"].dt.to_period("W").dt.start_time

# ---------- 1. VOLUME & TRIAGE ----------
volume = (recent.groupby(["Week", "Severity"], observed=True)
                .size().unstack(fill_value=0)
                .reindex(columns=SEVERITY_ORDER, fill_value=0))

fig, ax = plt.subplots(figsize=(10, 5))
volume.plot(kind="bar", stacked=True, ax=ax,
            color=[SEVERITY_COLORS[s] for s in SEVERITY_ORDER])
ax.set_title(f"Alert Volume by Week & Severity (Last {LOOKBACK_DAYS} Days)")
ax.set_xlabel("Week"); ax.set_ylabel("Alert Count")
ax.set_xticklabels([d.strftime("%b %d") for d in volume.index], rotation=45)
ax.legend(title="Severity")
plt.tight_layout(); plt.savefig(CHART_DIR / "volume.png", dpi=150); plt.close()

# Status breakdown
status_counts = recent["Status"].value_counts().to_dict()
total = len(recent)
completed = recent[recent["Status"].isin(COMPLETED_STATUSES)]
issues = recent[recent["Status"] == TRUE_POSITIVE_STATUS]
issue_rate = (len(issues) / len(completed) * 100) if len(completed) else 0

# ---------- 2. ALERT RULE BREAKDOWN ----------
rule_col = next((c for c in recent.columns if "rule" in c.lower()), "Alert Rule")
rule_counts = recent[rule_col].value_counts().head(15)

fig, ax = plt.subplots(figsize=(10, 6))
rule_counts.plot(kind="barh", ax=ax, color="steelblue")
ax.invert_yaxis()
ax.set_title("Top Alert Rules (Last 90 Days)")
ax.set_xlabel("Count")
plt.tight_layout(); plt.savefig(CHART_DIR / "rules.png", dpi=150); plt.close()

# Issue rate by rule (which rules actually catch real issues)
rule_issue = (recent.assign(IsIssue=recent["Status"].eq(TRUE_POSITIVE_STATUS))
                    .groupby(rule_col)
                    .agg(Total=("Status", "size"), Issues=("IsIssue", "sum")))
rule_issue["IssueRate%"] = (rule_issue["Issues"] / rule_issue["Total"] * 100).round(1)
rule_issue = rule_issue.sort_values("Total", ascending=False).head(10)

# ---------- 3. ANALYST PRODUCTIVITY ----------
analyst_col = next((c for c in recent.columns if "analyst" in c.lower()), "Analyst Name")
analyst_counts = (completed[analyst_col].value_counts())

fig, ax = plt.subplots(figsize=(10, 5))
analyst_counts.plot(kind="bar", ax=ax, color="seagreen")
ax.set_title("Alerts Completed by Analyst (Last 90 Days)")
ax.set_xlabel("Analyst"); ax.set_ylabel("Completed Alerts")
plt.xticks(rotation=45, ha="right")
plt.tight_layout(); plt.savefig(CHART_DIR / "analyst.png", dpi=150); plt.close()

# ---------- BUILD PDF ----------
class PDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, "Insider Enhanced Surveillance — Weekly Report", ln=True)
        self.set_font("Helvetica", "", 10)
        self.cell(0, 6, f"Generated: {datetime.now().strftime('%B %d, %Y')}", ln=True)
        self.ln(4)
    def footer(self):
        self.set_y(-12); self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")
    def section(self, title):
        self.set_font("Helvetica", "B", 12)
        self.set_fill_color(230, 230, 230)
        self.cell(0, 8, title, ln=True, fill=True); self.ln(2)
    def kv(self, k, v):
        self.set_font("Helvetica", "", 10)
        self.cell(0, 6, f"   {k}: {v}", ln=True)

pdf = PDF(); pdf.add_page()

# 1. Volume & Triage
pdf.section("1. Volume & Triage Metrics")
pdf.kv("Total alerts (period)", total)
pdf.kv("Reviewing (open)", status_counts.get("Reviewing", 0))
pdf.kv("Non-issue (closed)", status_counts.get("Non-issue", 0))
pdf.kv("Issue (true positive)", status_counts.get("Issue", 0))
pdf.kv("Issue rate (Issue / Completed)", f"{issue_rate:.1f}%")
pdf.ln(2); pdf.image(str(CHART_DIR / "volume.png"), w=180)

# 2. Rule Breakdown
pdf.add_page()
pdf.section("2. Alert Rule Type Breakdown")
pdf.image(str(CHART_DIR / "rules.png"), w=180)
pdf.ln(4)
pdf.section("Issue Rate by Top Rules")
pdf.set_font("Courier", "", 9)
pdf.cell(0, 5, f"{'Rule':<45}{'Total':>8}{'Issues':>8}{'Rate%':>8}", ln=True)
for rule, row in rule_issue.iterrows():
    name = (str(rule)[:42] + "...") if len(str(rule)) > 45 else str(rule)
    pdf.cell(0, 5, f"{name:<45}{int(row['Total']):>8}{int(row['Issues']):>8}{row['IssueRate%']:>8}", ln=True)

# 3. Analyst
pdf.add_page()
pdf.section("3. Alerts Completed by Analyst")
pdf.image(str(CHART_DIR / "analyst.png"), w=180)

# 4. Highlights
pdf.add_page()
pdf.section("4. Program Highlights")
pdf.set_font("Helvetica", "", 10)
pdf.multi_cell(0, 6, PROGRAM_HIGHLIGHTS)

pdf.output(OUTPUT_PDF)
print(f"✅ Report generated: {OUTPUT_PDF}")
