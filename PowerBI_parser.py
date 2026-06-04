# power.py — IES 90-Day Operational Report (Proofpoint)
import os
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

# ---------- CONFIG ----------
CSV_PATH   = "alerts.csv"      # <-- your CSV filename
LOGO_PATH  = "td.png"
CHART_DIR  = "charts"
LOOKBACK   = 90

# EXACT columns from your file
COL_DATE     = "Alert Date"
COL_CREATED  = "Created"
COL_STATUS   = "Status"
COL_RULE     = "Alert Rule"
COL_SEVERITY = "Severity"
COL_ANALYST  = "Analyst Name"
COL_SIGNOFF  = "Sign-off status"

end   = datetime.now().date()
start = end - timedelta(days=LOOKBACK)
window_label = f"{start:%m/%d/%Y} – {end:%m/%d/%Y}"
OUTPUT_DOCX  = f"IES_90DayReport_{end:%Y-%m-%d}.docx"
os.makedirs(CHART_DIR, exist_ok=True)

# ---------- LOAD ----------
df = pd.read_csv(CSV_PATH)
df[COL_DATE] = pd.to_datetime(df[COL_DATE], errors="coerce")
df = df.dropna(subset=[COL_DATE])
df = df[(df[COL_DATE].dt.date >= start) & (df[COL_DATE].dt.date <= end)]

# ---------- METRICS ----------
alerts_received = len(df)
alerts_pending  = df[COL_STATUS].astype(str).str.lower().eq("pending").sum()
avg_per_day     = round(alerts_received / LOOKBACK, 1)

status_counts   = df[df[COL_STATUS].isin(["Non-Issue", "Issue"])][COL_STATUS].value_counts()
severity_counts = df[COL_SEVERITY].value_counts()

rule_counts = df[COL_RULE].value_counts()
top5  = rule_counts.head(5)
other = rule_counts.iloc[5:].sum()
rules_plot = pd.concat([top5, pd.Series({"Others": other})]) if other else top5

analyst_counts = (df[df[COL_STATUS].isin(["Non-Issue", "Issue"])]
                  [COL_ANALYST].value_counts())

# ---------- CHARTS ----------
TD_GREEN = "#00B140"
plt.rcParams.update({"font.family": "Calibri", "font.size": 11})

def save_bar(series, fname, ylabel, xlabel):
    if series.empty: return
    fig, ax = plt.subplots(figsize=(8, 4.2))
    bars = ax.bar(series.index.astype(str), series.values, color=TD_GREEN)
    ax.bar_label(bars, padding=3)
    ax.set_ylabel(ylabel); ax.set_xlabel(xlabel)
    ax.spines[["top","right"]].set_visible(False)
    plt.xticks(rotation=15, ha="right")
    plt.tight_layout(); plt.savefig(f"{CHART_DIR}/{fname}", dpi=160); plt.close()

def save_pie(series, fname):
    if series.empty: return
    fig, ax = plt.subplots(figsize=(6, 4.2))
    palette = ["#E8B22E","#B0413E","#2D2D2D","#7FB539","#5A8FBF","#888888"]
    ax.pie(series.values,
           labels=[f"{i} ({v}, {v/series.sum():.1%})"
                   for i, v in zip(series.index, series.values)],
           colors=palette[:len(series)])
    plt.tight_layout(); plt.savefig(f"{CHART_DIR}/{fname}", dpi=160); plt.close()

save_pie(severity_counts, "severity.png")
save_bar(status_counts,   "status.png",   "Alerts (90d)",       "Status")
save_bar(rules_plot,      "rules.png",    "Volume of Alerts",   "Alert Rule")
save_bar(analyst_counts,  "analysts.png", "Alerts Completed",   "Analyst")

# ---------- DOC ----------
doc = Document()

hdr = doc.sections[0].header.paragraphs[0]
hdr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
if os.path.exists(LOGO_PATH):
    hdr.add_run().add_picture(LOGO_PATH, width=Inches(0.7))

def new_page(title):
    doc.add_page_break()
    p = doc.add_paragraph()
    r = p.add_run("Insider Enhanced Surveillance")
    r.bold = True; r.font.size = Pt(22)
    doc.add_paragraph(f"90-Day Operational Report | {title}\n{window_label}")

# Cover
p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("\n\n\n\nInsider Enhanced Surveillance\n"
              "90-Day Operational Report – Proofpoint\n")
r.bold = True; r.font.size = Pt(28)
c = doc.add_paragraph(window_label); c.alignment = WD_ALIGN_PARAGRAPH.CENTER

# Volume & Triage
new_page("Volume and Triage Metrics")
doc.add_paragraph(f"Alerts Received: {alerts_received}    "
                  f"Alerts Pending: {alerts_pending}    "
                  f"Avg/day: {avg_per_day}")
if os.path.exists(f"{CHART_DIR}/severity.png"):
    doc.add_picture(f"{CHART_DIR}/severity.png", width=Inches(3.2))
if os.path.exists(f"{CHART_DIR}/status.png"):
    doc.add_picture(f"{CHART_DIR}/status.png", width=Inches(3.2))

# Rules
new_page("Alerts by Rule Type Breakdown")
if os.path.exists(f"{CHART_DIR}/rules.png"):
    doc.add_picture(f"{CHART_DIR}/rules.png", width=Inches(6.5))

# Analyst
new_page("Alerts Completed by Analyst")
if os.path.exists(f"{CHART_DIR}/analysts.png"):
    doc.add_picture(f"{CHART_DIR}/analysts.png", width=Inches(6.5))

# Highlights
new_page("Program Highlights")
doc.add_paragraph("[ADD ACCOMPLISHMENTS HERE BEFORE EXPORTING TO PDF]")
doc.add_paragraph(f"There were {int(status_counts.get('Issue', 0))} "
                  f"identified issues over the 90-day period.")

doc.save(OUTPUT_DOCX)
print(f"Saved {OUTPUT_DOCX}")
