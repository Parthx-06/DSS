import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

import pandas as pd
import requests
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")

# ═══════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "").replace(" ", "")
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
MANAGER_EMAIL = os.getenv("MANAGER_EMAIL")
SUPPLIER_EMAIL = os.getenv("SUPPLIER_EMAIL", MANAGER_EMAIL)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ═══════════════════════════════════════════════════
# IN-MEMORY STATE FOR AGENTIC PIPELINE
# ═══════════════════════════════════════════════════
pipeline_state = {
    "status": "idle",
    "steps": [],
    "data": None,
    "charts": None,
    "news": None,
    "predictions": None,
    "anomalies": None,
    "report_sent": False,
    "supplier_alerted": False,
    "last_run": None
}


# ═══════════════════════════════════════════════════
# MODULE 1: GENERIC CSV ANALYSIS ENGINE
# ═══════════════════════════════════════════════════
def _detect_columns(df):
    """Auto-detect column roles: numeric, categorical, time-like."""
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = []
    time_cols = []
    for col in df.columns:
        if col in numeric_cols:
            continue
        nunique = df[col].nunique()
        # Try parsing as date
        try:
            pd.to_datetime(df[col], infer_datetime_format=True)
            time_cols.append(col)
            continue
        except Exception:
            pass
        # Month-name check
        month_names = {"jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec",
                       "january","february","march","april","may","june","july","august","september","october","november","december"}
        vals_lower = set(str(v).strip().lower() for v in df[col].dropna().unique())
        if vals_lower and vals_lower.issubset(month_names):
            time_cols.append(col)
            continue
        if nunique <= 50 and nunique < len(df) * 0.5:
            cat_cols.append(col)
    return numeric_cols, cat_cols, time_cols


def analyze_csv(filepath):
    """Extract features from ANY CSV — fully generic."""
    df = pd.read_csv(filepath)
    numeric_cols, cat_cols, time_cols = _detect_columns(df)

    # Pick primary roles (best guesses)
    primary_num = numeric_cols[0] if numeric_cols else None
    secondary_num = numeric_cols[1] if len(numeric_cols) >= 2 else None
    primary_cat = cat_cols[0] if cat_cols else None
    secondary_cat = cat_cols[1] if len(cat_cols) >= 2 else None
    time_col = time_cols[0] if time_cols else None

    # Order time values if month-like
    time_labels = []
    if time_col:
        month_order = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        raw_vals = df[time_col].dropna().unique().tolist()
        # Check if short month names
        short_map = {m.lower(): m for m in month_order}
        ordered = [short_map[str(v).strip().lower()] for v in raw_vals if str(v).strip().lower() in short_map]
        if ordered:
            time_labels = [m for m in month_order if m in ordered]
        else:
            try:
                parsed = sorted(pd.to_datetime(raw_vals))
                time_labels = [str(v) for v in parsed]
            except Exception:
                time_labels = [str(v) for v in raw_vals]

    analysis = {
        "shape": {"rows": len(df), "columns": len(df.columns)},
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "numeric_cols": numeric_cols,
        "cat_cols": cat_cols,
        "time_cols": time_cols,
        "primary_num": primary_num,
        "secondary_num": secondary_num,
        "primary_cat": primary_cat,
        "secondary_cat": secondary_cat,
        "time_col": time_col,
        "time_labels": time_labels,
        "summary_stats": {},
        "category_values": {},
        "category_stats": {},
        "time_stats": {},
        "growth_rates": {},
        "correlations": {},
        # KPI helpers
        "kpi_total_1": 0,
        "kpi_total_2": 0,
        "kpi_ratio": 0,
        "kpi_top": "",
        "kpi_bottom": "",
        "kpi_labels": {},
    }

    # Stats for every numeric column
    for col in numeric_cols:
        s = df[col].dropna()
        analysis["summary_stats"][col] = {
            "mean": round(float(s.mean()), 2),
            "median": round(float(s.median()), 2),
            "std": round(float(s.std()), 2) if len(s) > 1 else 0,
            "min": round(float(s.min()), 2),
            "max": round(float(s.max()), 2),
            "sum": round(float(s.sum()), 2),
        }

    # Category values and per-category stats
    for cc in cat_cols:
        vals = sorted(df[cc].dropna().unique().tolist(), key=str)
        analysis["category_values"][cc] = vals
        analysis["category_stats"][cc] = {}
        grp = df.groupby(cc)
        for val in vals:
            gdata = grp.get_group(val)
            stats = {}
            for nc in numeric_cols:
                if nc in gdata.columns:
                    stats[nc] = {
                        "sum": round(float(gdata[nc].sum()), 2),
                        "mean": round(float(gdata[nc].mean()), 2),
                        "std": round(float(gdata[nc].std()), 2) if len(gdata) > 1 else 0,
                    }
            analysis["category_stats"][cc][str(val)] = stats

    # Time-based stats
    if time_col and primary_num:
        for t in time_labels:
            tdata = df[df[time_col].astype(str).str.strip().str.lower() == str(t).strip().lower()]
            ts_dict = {}
            for nc in numeric_cols:
                if nc in tdata.columns:
                    ts_dict[nc] = round(float(tdata[nc].sum()), 2)
            analysis["time_stats"][str(t)] = ts_dict

    # Growth rates (per category over time)
    if time_col and primary_cat and primary_num and len(time_labels) >= 2:
        for val in analysis["category_values"].get(primary_cat, []):
            sub = df[df[primary_cat] == val]
            rates = []
            for i in range(1, len(time_labels)):
                prev_t, curr_t = time_labels[i-1], time_labels[i]
                pv_data = sub[sub[time_col].astype(str).str.strip().str.lower() == str(prev_t).strip().lower()]
                cv_data = sub[sub[time_col].astype(str).str.strip().str.lower() == str(curr_t).strip().lower()]
                pv = float(pv_data[primary_num].sum()) if len(pv_data) > 0 else 0
                cv = float(cv_data[primary_num].sum()) if len(cv_data) > 0 else 0
                rate = ((cv - pv) / pv * 100) if pv > 0 else 0
                rates.append(round(rate, 2))
            analysis["growth_rates"][str(val)] = rates

    # KPI helpers
    if primary_num:
        analysis["kpi_total_1"] = round(float(df[primary_num].sum()), 2)
        analysis["kpi_labels"]["total_1"] = f"Total {primary_num}"
    if secondary_num:
        analysis["kpi_total_2"] = round(float(df[secondary_num].sum()), 2)
        analysis["kpi_labels"]["total_2"] = f"Total {secondary_num}"
    if primary_num and secondary_num:
        t1 = analysis["kpi_total_1"]
        t2 = analysis["kpi_total_2"]
        analysis["kpi_ratio"] = round((t2 / t1 * 100) if t1 > 0 else 0, 2)
        analysis["kpi_labels"]["ratio"] = f"{secondary_num}/{primary_num} %"
    if primary_cat and primary_num:
        grp_sum = df.groupby(primary_cat)[primary_num].sum()
        analysis["kpi_top"] = str(grp_sum.idxmax()) if len(grp_sum) > 0 else ""
        analysis["kpi_bottom"] = str(grp_sum.idxmin()) if len(grp_sum) > 0 else ""
        analysis["kpi_labels"]["top"] = f"Top {primary_cat}"

    # Correlations
    if len(numeric_cols) >= 2:
        corr = df[numeric_cols].corr()
        for col in numeric_cols:
            analysis["correlations"][col] = {c2: round(float(corr.loc[col, c2]), 3) for c2 in numeric_cols}

    return analysis, df


# ═══════════════════════════════════════════════════
# MODULE 2: GENERIC CHART DATA GENERATOR (up to 10)
# ═══════════════════════════════════════════════════
def generate_chart_data(analysis, df):
    """Auto-generate up to 10 Chart.js chart configs from ANY CSV."""
    charts = {}
    nc = analysis.get("numeric_cols", [])
    cc = analysis.get("cat_cols", [])
    tc = analysis.get("time_col")
    tl = analysis.get("time_labels", [])
    pn = analysis.get("primary_num")
    sn = analysis.get("secondary_num")
    pc = analysis.get("primary_cat")
    sc = analysis.get("secondary_cat")
    cat_vals = analysis.get("category_values", {})
    cat_stats = analysis.get("category_stats", {})

    palette = [
        {"bg": "rgba(99,102,241,0.7)", "border": "#6366f1"},
        {"bg": "rgba(236,72,153,0.7)", "border": "#ec4899"},
        {"bg": "rgba(34,211,238,0.7)", "border": "#22d3ee"},
        {"bg": "rgba(168,85,247,0.7)", "border": "#a855f7"},
        {"bg": "rgba(251,146,60,0.7)", "border": "#fb923c"},
        {"bg": "rgba(52,211,153,0.7)", "border": "#34d399"},
        {"bg": "rgba(251,191,36,0.7)", "border": "#fbbf24"},
        {"bg": "rgba(239,68,68,0.7)", "border": "#ef4444"},
    ]
    def p(i): return palette[i % len(palette)]

    chart_num = 0

    # ── 1. Bar: primary_num by primary_cat ──
    if pc and pn:
        vals = cat_vals.get(pc, [])
        charts[f"chart_{chart_num}"] = {
            "type": "bar",
            "title": f"Total {pn} by {pc}",
            "data": {
                "labels": [str(v) for v in vals],
                "datasets": [{"label": f"Total {pn}",
                    "data": [cat_stats.get(pc, {}).get(str(v), {}).get(pn, {}).get("sum", 0) for v in vals],
                    "backgroundColor": [p(i)["bg"] for i in range(len(vals))],
                    "borderColor": [p(i)["border"] for i in range(len(vals))],
                    "borderWidth": 2, "borderRadius": 8}],
            },
        }
        chart_num += 1

    # ── 2. Line: primary_num over time (per primary_cat if available) ──
    if tc and pn:
        datasets = []
        if pc:
            for i, val in enumerate(cat_vals.get(pc, [])):
                sub = df[df[pc] == val]
                data_pts = []
                for t in tl:
                    td = sub[sub[tc].astype(str).str.strip().str.lower() == str(t).strip().lower()]
                    data_pts.append(round(float(td[pn].sum()), 2) if len(td) > 0 else 0)
                datasets.append({"label": str(val), "data": data_pts,
                    "borderColor": p(i)["border"], "backgroundColor": p(i)["bg"],
                    "tension": 0.4, "fill": False, "pointRadius": 5, "pointHoverRadius": 8})
        else:
            data_pts = []
            for t in tl:
                td = df[df[tc].astype(str).str.strip().str.lower() == str(t).strip().lower()]
                data_pts.append(round(float(td[pn].sum()), 2) if len(td) > 0 else 0)
            datasets.append({"label": pn, "data": data_pts,
                "borderColor": p(0)["border"], "backgroundColor": p(0)["bg"],
                "tension": 0.4, "fill": False, "pointRadius": 5})
        charts[f"chart_{chart_num}"] = {
            "type": "line", "title": f"{pn} Trend Over Time",
            "data": {"labels": [str(t) for t in tl], "datasets": datasets},
        }
        chart_num += 1

    # ── 3. Pie: primary_num distribution by primary_cat ──
    if pc and pn:
        vals = cat_vals.get(pc, [])
        charts[f"chart_{chart_num}"] = {
            "type": "pie", "title": f"{pn} Distribution by {pc}",
            "data": {"labels": [str(v) for v in vals],
                "datasets": [{"data": [cat_stats.get(pc, {}).get(str(v), {}).get(pn, {}).get("sum", 0) for v in vals],
                    "backgroundColor": [p(i)["bg"] for i in range(len(vals))],
                    "borderColor": ["rgba(10,14,26,0.8)"] * len(vals), "borderWidth": 3}]},
        }
        chart_num += 1

    # ── 4. Grouped Bar: primary_num by secondary_cat, grouped by primary_cat ──
    if pc and sc and pn:
        pc_vals = cat_vals.get(pc, [])
        sc_vals = cat_vals.get(sc, [])
        datasets = []
        for i, pv in enumerate(pc_vals):
            data_pts = []
            for sv in sc_vals:
                sub = df[(df[pc] == pv) & (df[sc] == sv)]
                data_pts.append(round(float(sub[pn].sum()), 2) if len(sub) > 0 else 0)
            datasets.append({"label": str(pv), "data": data_pts,
                "backgroundColor": p(i)["bg"], "borderColor": p(i)["border"], "borderWidth": 2, "borderRadius": 6})
        charts[f"chart_{chart_num}"] = {
            "type": "bar", "title": f"{pn} by {sc} (per {pc})",
            "data": {"labels": [str(v) for v in sc_vals], "datasets": datasets},
        }
        chart_num += 1
    elif pc and pn and len(nc) >= 2:
        # Alternate: second numeric by primary_cat
        n2 = nc[1]
        vals = cat_vals.get(pc, [])
        charts[f"chart_{chart_num}"] = {
            "type": "bar", "title": f"Total {n2} by {pc}",
            "data": {"labels": [str(v) for v in vals],
                "datasets": [{"label": f"Total {n2}",
                    "data": [cat_stats.get(pc, {}).get(str(v), {}).get(n2, {}).get("sum", 0) for v in vals],
                    "backgroundColor": [p(i+3)["bg"] for i in range(len(vals))],
                    "borderColor": [p(i+3)["border"] for i in range(len(vals))],
                    "borderWidth": 2, "borderRadius": 8}]},
        }
        chart_num += 1

    # ── 5. Line: secondary_num over time (area fill) ──
    if tc and sn:
        datasets = []
        if pc:
            for i, val in enumerate(cat_vals.get(pc, [])):
                sub = df[df[pc] == val]
                data_pts = []
                for t in tl:
                    td = sub[sub[tc].astype(str).str.strip().str.lower() == str(t).strip().lower()]
                    data_pts.append(round(float(td[sn].sum()), 2) if len(td) > 0 else 0)
                datasets.append({"label": str(val), "data": data_pts,
                    "borderColor": p(i)["border"], "backgroundColor": p(i)["bg"].replace("0.7", "0.15"),
                    "tension": 0.4, "fill": True, "pointRadius": 5})
        else:
            data_pts = [analysis.get("time_stats", {}).get(str(t), {}).get(sn, 0) for t in tl]
            datasets.append({"label": sn, "data": data_pts,
                "borderColor": p(1)["border"], "backgroundColor": p(1)["bg"].replace("0.7", "0.15"),
                "tension": 0.4, "fill": True, "pointRadius": 5})
        charts[f"chart_{chart_num}"] = {
            "type": "line", "title": f"{sn} Trend Over Time",
            "data": {"labels": [str(t) for t in tl], "datasets": datasets},
        }
        chart_num += 1

    # ── 6. Horizontal Bar: mean of primary_num by primary_cat ──
    if pc and pn:
        vals = cat_vals.get(pc, [])
        charts[f"chart_{chart_num}"] = {
            "type": "bar", "title": f"Avg {pn} by {pc}",
            "indexAxis": "y",
            "data": {"labels": [str(v) for v in vals],
                "datasets": [{"label": f"Average {pn}",
                    "data": [cat_stats.get(pc, {}).get(str(v), {}).get(pn, {}).get("mean", 0) for v in vals],
                    "backgroundColor": [p(i+2)["bg"] for i in range(len(vals))],
                    "borderRadius": 6, "borderWidth": 0}]},
        }
        chart_num += 1

    # ── 7. Stacked Bar: time × secondary_cat (or categories) ──
    if tc and pn and (sc or pc):
        grp_col = sc if sc else pc
        grp_vals = cat_vals.get(grp_col, [])
        datasets = []
        for i, gv in enumerate(grp_vals):
            sub = df[df[grp_col] == gv]
            data_pts = []
            for t in tl:
                td = sub[sub[tc].astype(str).str.strip().str.lower() == str(t).strip().lower()]
                data_pts.append(round(float(td[pn].sum()), 2) if len(td) > 0 else 0)
            datasets.append({"label": str(gv), "data": data_pts,
                "backgroundColor": p(i)["bg"], "borderColor": p(i)["border"], "borderWidth": 1})
        charts[f"chart_{chart_num}"] = {
            "type": "bar", "title": f"{pn} Over Time by {grp_col}",
            "stacked": True,
            "data": {"labels": [str(t) for t in tl], "datasets": datasets},
        }
        chart_num += 1

    # ── 8. Doughnut: secondary grouping ──
    if sc and pn:
        vals = cat_vals.get(sc, [])
        charts[f"chart_{chart_num}"] = {
            "type": "doughnut", "title": f"{pn} by {sc}",
            "data": {"labels": [str(v) for v in vals],
                "datasets": [{"data": [cat_stats.get(sc, {}).get(str(v), {}).get(pn, {}).get("sum", 0) for v in vals],
                    "backgroundColor": [p(i)["bg"] for i in range(len(vals))],
                    "borderColor": ["rgba(10,14,26,0.8)"] * len(vals), "borderWidth": 3, "cutout": "65%"}]},
        }
        chart_num += 1
    elif pc and pn and not sc:
        # Doughnut of primary_cat with secondary_num (or same num)
        num_to_use = sn if sn else pn
        vals = cat_vals.get(pc, [])
        charts[f"chart_{chart_num}"] = {
            "type": "doughnut", "title": f"{num_to_use} Share by {pc}",
            "data": {"labels": [str(v) for v in vals],
                "datasets": [{"data": [cat_stats.get(pc, {}).get(str(v), {}).get(num_to_use, {}).get("sum", 0) for v in vals],
                    "backgroundColor": [p(i+2)["bg"] for i in range(len(vals))],
                    "borderColor": ["rgba(10,14,26,0.8)"] * len(vals), "borderWidth": 3, "cutout": "65%"}]},
        }
        chart_num += 1

    # ── 9. Radar: multi-metric scorecard per primary_cat ──
    if pc and len(nc) >= 2:
        vals = cat_vals.get(pc, [])
        metrics = nc[:5]  # up to 5 numeric columns
        # Normalize
        maxes = {}
        for m in metrics:
            mx = max([cat_stats.get(pc, {}).get(str(v), {}).get(m, {}).get("sum", 0) for v in vals] or [1])
            maxes[m] = mx if mx > 0 else 1
        datasets = []
        for i, val in enumerate(vals):
            data_pts = []
            for m in metrics:
                raw = cat_stats.get(pc, {}).get(str(val), {}).get(m, {}).get("sum", 0)
                data_pts.append(round(raw / maxes[m] * 100, 1))
            datasets.append({"label": str(val), "data": data_pts,
                "borderColor": p(i)["border"], "backgroundColor": p(i)["bg"].replace("0.7", "0.2"),
                "pointBackgroundColor": p(i)["border"], "pointBorderColor": "#fff", "pointHoverRadius": 6})
        charts[f"chart_{chart_num}"] = {
            "type": "radar", "title": "Multi-Metric Scorecard",
            "data": {"labels": metrics, "datasets": datasets},
        }
        chart_num += 1

    # ── 10. Growth Rate Trajectory ──
    if analysis.get("growth_rates"):
        gr = analysis["growth_rates"]
        growth_labels = [f"{tl[i]}→{tl[i+1]}" for i in range(len(tl)-1)] if len(tl) >= 2 else [f"Period {i+1}" for i in range(max(len(v) for v in gr.values()))]
        datasets = []
        for i, (key, rates) in enumerate(gr.items()):
            datasets.append({"label": str(key), "data": rates,
                "borderColor": p(i)["border"], "backgroundColor": p(i)["bg"].replace("0.7", "0.2"),
                "tension": 0.4, "fill": True, "pointRadius": 6, "pointHoverRadius": 9})
        charts[f"chart_{chart_num}"] = {
            "type": "line", "title": "Growth Rate Trajectory (%)",
            "data": {"labels": growth_labels, "datasets": datasets},
        }
        chart_num += 1

    # ── Fill remaining slots with extra numeric charts ──
    for extra_n in nc[2:]:
        if chart_num >= 10:
            break
        if pc:
            vals = cat_vals.get(pc, [])
            charts[f"chart_{chart_num}"] = {
                "type": "bar", "title": f"{extra_n} by {pc}",
                "data": {"labels": [str(v) for v in vals],
                    "datasets": [{"label": extra_n,
                        "data": [cat_stats.get(pc, {}).get(str(v), {}).get(extra_n, {}).get("sum", 0) for v in vals],
                        "backgroundColor": [p(i+chart_num)["bg"] for i in range(len(vals))],
                        "borderRadius": 6, "borderWidth": 0}]},
            }
            chart_num += 1

    # If we have very few charts (no categories), create numeric distribution charts
    if chart_num < 3 and nc:
        for col in nc[:min(5, 10 - chart_num)]:
            vals = df[col].dropna().tolist()
            # Create histogram-like bins
            n_bins = min(15, len(set(vals)))
            if n_bins > 1:
                hist, edges = pd.cut(vals, bins=n_bins, retbins=True)
                counts = hist.value_counts().sort_index()
                labels = [f"{edges[i]:.1f}-{edges[i+1]:.1f}" for i in range(len(edges)-1)]
                charts[f"chart_{chart_num}"] = {
                    "type": "bar", "title": f"{col} Distribution",
                    "data": {"labels": labels,
                        "datasets": [{"label": "Frequency", "data": counts.tolist(),
                            "backgroundColor": p(chart_num)["bg"], "borderRadius": 4, "borderWidth": 0}]},
                }
                chart_num += 1

    return charts


# ═══════════════════════════════════════════════════
# MODULE 3: NEWS INTELLIGENCE (News API)
# ═══════════════════════════════════════════════════
def fetch_market_news(products):
    """Fetch product-related market news using Google News RSS (Free & reliable)."""
    import xml.etree.ElementTree as ET
    import urllib.parse
    all_articles = []
    
    for product in products:
        try:
            query = urllib.parse.quote(f"{product} business market")
            resp = requests.get(f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en", timeout=10)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.findall('.//item')[:3]:
                    all_articles.append({
                        "product": product,
                        "title": item.find('title').text,
                        "description": item.find('title').text,
                        "source": item.find('source').text if item.find('source') is not None else "Google News",
                        "url": item.find('link').text,
                        "publishedAt": item.find('pubDate').text,
                        "image": "",
                    })
        except Exception:
            pass

    if not all_articles:
        try:
            resp = requests.get("https://news.google.com/rss/search?q=business+market&hl=en-US&gl=US&ceid=US:en", timeout=10)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.findall('.//item')[:5]:
                    all_articles.append({
                        "product": "General Market",
                        "title": item.find('title').text,
                        "description": item.find('title').text,
                        "source": item.find('source').text if item.find('source') is not None else "Google News",
                        "url": item.find('link').text,
                        "publishedAt": item.find('pubDate').text,
                        "image": "",
                    })
        except Exception:
            pass
            
    return {"articles": all_articles, "count": len(all_articles)}


# ═══════════════════════════════════════════════════
# MODULE 4: GEMINI PREDICTION ENGINE
# ═══════════════════════════════════════════════════
def predict_market(analysis, news_data):
    """Combine CSV analysis + news → Gemini → structured market forecast."""
    news_summary = ""
    for a in news_data.get("articles", [])[:15]:
        news_summary += f"- [{a.get('product','')}] {a['title']}: {a.get('description','')}\n"

    pc = analysis.get("primary_cat", "Category")
    pn = analysis.get("primary_num", "Value")
    cat_items = list(analysis.get("category_values", {}).get(pc, [])) if pc else []

    prompt = f"""You are an expert business analyst and market predictor.
Based on the following data analysis and recent market news, provide detailed predictions.

=== DATA ANALYSIS ===
Columns: {', '.join(analysis.get('columns', []))}
Rows: {analysis['shape']['rows']}
Primary Category ({pc}): {', '.join(str(x) for x in cat_items)}
Primary Metric ({pn}): Total = {analysis.get('kpi_total_1', 0):,.2f}
Secondary Metric: Total = {analysis.get('kpi_total_2', 0):,.2f}
Top {pc}: {analysis.get('kpi_top', 'N/A')}
Bottom {pc}: {analysis.get('kpi_bottom', 'N/A')}

Category Stats:
{json.dumps(analysis.get('category_stats', {}), indent=2)}

Growth Rates:
{json.dumps(analysis.get('growth_rates', {}), indent=2)}

Summary Stats:
{json.dumps(analysis.get('summary_stats', {}), indent=2)}

=== MARKET NEWS ===
{news_summary if news_summary else 'No recent news available.'}

=== INSTRUCTIONS ===
Return ONLY a JSON object (no markdown, no code fences):
{{
  "overall_outlook": "bullish/bearish/neutral",
  "confidence": 0-100,
  "summary": "2-3 sentence market summary",
  "product_predictions": [
    {{
      "product": "category value name",
      "trend": "increasing/decreasing/stable",
      "confidence": 0-100,
      "predicted_change_percent": number,
      "reasoning": "brief explanation",
      "action": "increase_stock/decrease_stock/maintain",
      "supplier_message": "message to send to supplier"
    }}
  ],
  "key_insights": ["insight1", "insight2", ...],
  "risk_factors": ["risk1", "risk2", ...],
  "recommendations": ["rec1", "rec2", ...]
}}"""

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "response_format": {"type": "json_object"}
            },
            timeout=20
        )
        data = resp.json()
        if "choices" not in data or len(data["choices"]) == 0:
            raise Exception(data.get("error", {}).get("message", "Unknown API Error"))
        text = data["choices"][0]["message"]["content"].strip()
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "overall_outlook": "neutral", "confidence": 50,
            "summary": "Parse error",
            "product_predictions": [], "key_insights": ["AI response could not be parsed as JSON"],
            "risk_factors": [], "recommendations": [],
        }
    except Exception as e:
        return {
            "overall_outlook": "error", "confidence": 0,
            "summary": f"Prediction failed via Groq: {e}",
            "product_predictions": [], "key_insights": [], "risk_factors": [], "recommendations": [],
        }


# ═══════════════════════════════════════════════════
# MODULE 5A: PARETO / ABC ANALYSIS
# ═══════════════════════════════════════════════════
def pareto_abc_analysis(analysis, df):
    """Classify categories into A/B/C tiers based on cumulative contribution."""
    pc = analysis.get("primary_cat")
    pn = analysis.get("primary_num")
    if not pc or not pn:
        return {"tiers": {}, "chart_data": {}}
    grp = df.groupby(pc)[pn].sum().sort_values(ascending=False)
    total = grp.sum()
    if total == 0:
        return {"tiers": {}, "chart_data": {}}
    cum = 0
    tiers = {}
    labels, values, cumulative, tier_colors = [], [], [], []
    color_map = {"A": "#34d399", "B": "#fbbf24", "C": "#ef4444"}
    for cat, val in grp.items():
        cum += val
        pct = cum / total * 100
        tier = "A" if pct <= 80 else ("B" if pct <= 95 else "C")
        tiers[str(cat)] = {"value": round(float(val), 2), "pct": round(float(val / total * 100), 2),
                           "cumulative_pct": round(float(pct), 2), "tier": tier}
        labels.append(str(cat))
        values.append(round(float(val), 2))
        cumulative.append(round(float(pct), 2))
        tier_colors.append(color_map[tier])
    return {"tiers": tiers, "chart_data": {"labels": labels, "values": values,
            "cumulative": cumulative, "tier_colors": tier_colors}}


# ═══════════════════════════════════════════════════
# MODULE 5B: STATISTICAL FORECASTING
# ═══════════════════════════════════════════════════
def statistical_forecast(analysis, df):
    """Linear regression + moving average forecast for time-series data."""
    tc = analysis.get("time_col")
    pn = analysis.get("primary_num")
    tl = analysis.get("time_labels", [])
    if not tc or not pn or len(tl) < 3:
        return {"forecast": [], "trend": "insufficient_data"}
    time_vals = []
    for t in tl:
        td = df[df[tc].astype(str).str.strip().str.lower() == str(t).strip().lower()]
        time_vals.append(round(float(td[pn].sum()), 2) if len(td) > 0 else 0)
    n = len(time_vals)
    x_mean = (n - 1) / 2
    y_mean = sum(time_vals) / n
    num = sum((i - x_mean) * (time_vals[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    slope = num / den if den != 0 else 0
    intercept = y_mean - slope * x_mean
    fitted = [round(intercept + slope * i, 2) for i in range(n)]
    residuals = [time_vals[i] - fitted[i] for i in range(n)]
    std_err = (sum(r ** 2 for r in residuals) / max(n - 2, 1)) ** 0.5
    forecast_periods = min(3, max(1, n // 3))
    forecasted = []
    for j in range(1, forecast_periods + 1):
        val = round(intercept + slope * (n - 1 + j), 2)
        forecasted.append({"period": f"F+{j}", "value": val,
                           "lower": round(val - 1.96 * std_err, 2),
                           "upper": round(val + 1.96 * std_err, 2)})
    ma_window = min(3, n)
    ma = [round(sum(time_vals[max(0, i - ma_window + 1):i + 1]) / min(i + 1, ma_window), 2) for i in range(n)]
    trend = "growing" if slope > 0 else ("declining" if slope < 0 else "flat")
    return {"actual": time_vals, "fitted": fitted, "moving_avg": ma, "forecast": forecasted,
            "slope": round(slope, 4), "intercept": round(intercept, 2), "std_error": round(std_err, 2),
            "trend": trend, "labels": tl}


# ═══════════════════════════════════════════════════
# MODULE 5C: SENSITIVITY ANALYSIS
# ═══════════════════════════════════════════════════
def sensitivity_analysis(analysis, df):
    """Compute sensitivity/elasticity of each category to changes."""
    pc = analysis.get("primary_cat")
    nc = analysis.get("numeric_cols", [])
    cat_stats = analysis.get("category_stats", {}).get(pc, {})
    if not pc or len(nc) < 1:
        return {"sensitivities": []}
    pn = analysis.get("primary_num")
    total = float(df[pn].sum()) if pn else 1
    results = []
    for cat, stats in cat_stats.items():
        cat_val = stats.get(pn, {}).get("sum", 0)
        cat_std = stats.get(pn, {}).get("std", 0)
        share = (cat_val / total * 100) if total > 0 else 0
        volatility = (cat_std / stats.get(pn, {}).get("mean", 1) * 100) if stats.get(pn, {}).get("mean", 0) > 0 else 0
        impact_10pct = round(cat_val * 0.1, 2)
        results.append({"category": cat, "current_value": round(cat_val, 2),
                        "share_pct": round(share, 2), "volatility_cv": round(volatility, 2),
                        "impact_of_10pct_change": impact_10pct,
                        "sensitivity_rank": round(share * (1 + volatility / 100), 2)})
    results.sort(key=lambda x: x["sensitivity_rank"], reverse=True)
    return {"sensitivities": results, "metric": pn}


# ═══════════════════════════════════════════════════
# MODULE 5D: DECISION MATRIX (WEIGHTED SCORING)
# ═══════════════════════════════════════════════════
def decision_matrix(analysis, df):
    """Multi-criteria weighted scoring of categories across numeric dimensions."""
    pc = analysis.get("primary_cat")
    nc = analysis.get("numeric_cols", [])
    cat_stats = analysis.get("category_stats", {}).get(pc, {})
    if not pc or len(nc) < 2:
        return {"matrix": [], "criteria": []}
    criteria = nc[:5]
    maxes = {}
    for c in criteria:
        vals = [cat_stats.get(cat, {}).get(c, {}).get("sum", 0) for cat in cat_stats]
        maxes[c] = max(vals) if vals and max(vals) > 0 else 1
    weight = 1.0 / len(criteria)
    matrix = []
    for cat, stats in cat_stats.items():
        scores = {}
        weighted_total = 0
        for c in criteria:
            raw = stats.get(c, {}).get("sum", 0)
            normalized = round((raw / maxes[c]) * 100, 1)
            scores[c] = {"raw": round(raw, 2), "normalized": normalized}
            weighted_total += normalized * weight
        matrix.append({"category": cat, "scores": scores, "weighted_total": round(weighted_total, 1)})
    matrix.sort(key=lambda x: x["weighted_total"], reverse=True)
    for i, m in enumerate(matrix):
        m["rank"] = i + 1
    return {"matrix": matrix, "criteria": criteria, "weight_per_criteria": round(weight * 100, 1)}


# ═══════════════════════════════════════════════════
# MODULE 5E: RISK SCORING ENGINE
# ═══════════════════════════════════════════════════
def risk_scoring(analysis, df):
    """Composite risk score per category based on volatility, growth, concentration."""
    pc = analysis.get("primary_cat")
    pn = analysis.get("primary_num")
    cat_stats = analysis.get("category_stats", {}).get(pc, {})
    growth = analysis.get("growth_rates", {})
    if not pc or not pn:
        return {"risks": []}
    total = float(df[pn].sum()) if pn else 1
    risks = []
    for cat, stats in cat_stats.items():
        cat_val = stats.get(pn, {}).get("sum", 0)
        cat_std = stats.get(pn, {}).get("std", 0)
        cat_mean = stats.get(pn, {}).get("mean", 1)
        cv = (cat_std / cat_mean * 100) if cat_mean > 0 else 0
        concentration = (cat_val / total * 100) if total > 0 else 0
        gr = growth.get(str(cat), [])
        avg_growth = sum(gr) / len(gr) if gr else 0
        growth_vol = (sum((g - avg_growth) ** 2 for g in gr) / len(gr)) ** 0.5 if gr else 0
        vol_score = min(cv / 50 * 40, 40)
        conc_score = min(concentration / 30 * 30, 30)
        growth_score = min(growth_vol / 20 * 30, 30)
        risk_total = round(vol_score + conc_score + growth_score, 1)
        level = "HIGH" if risk_total > 60 else ("MEDIUM" if risk_total > 30 else "LOW")
        risks.append({"category": cat, "risk_score": risk_total, "risk_level": level,
                       "volatility_score": round(vol_score, 1), "concentration_score": round(conc_score, 1),
                       "growth_instability_score": round(growth_score, 1),
                       "cv_pct": round(cv, 1), "share_pct": round(concentration, 1)})
    risks.sort(key=lambda x: x["risk_score"], reverse=True)
    return {"risks": risks}


# ═══════════════════════════════════════════════════
# MODULE 5F: CONCENTRATION INDEX (HHI)
# ═══════════════════════════════════════════════════
def concentration_index(analysis, df):
    """Herfindahl-Hirschman Index measuring revenue concentration risk."""
    pc = analysis.get("primary_cat")
    pn = analysis.get("primary_num")
    if not pc or not pn:
        return {"hhi": 0, "interpretation": "N/A"}
    grp = df.groupby(pc)[pn].sum()
    total = grp.sum()
    if total == 0:
        return {"hhi": 0, "interpretation": "N/A"}
    shares = [(v / total * 100) for v in grp.values]
    hhi = round(sum(s ** 2 for s in shares), 1)
    if hhi > 2500:
        interp = "Highly Concentrated — significant dependency risk"
    elif hhi > 1500:
        interp = "Moderately Concentrated — some dependency risk"
    else:
        interp = "Well Diversified — low concentration risk"
    return {"hhi": hhi, "max_possible": 10000, "interpretation": interp,
            "shares": [{"category": str(c), "share": round(s, 2)} for c, s in zip(grp.index, shares)]}


# ═══════════════════════════════════════════════════
# MODULE 5G: COMPARATIVE PERIOD ANALYSIS
# ═══════════════════════════════════════════════════
def period_comparison(analysis, df):
    """Compare first-half vs second-half performance."""
    tc = analysis.get("time_col")
    pn = analysis.get("primary_num")
    pc = analysis.get("primary_cat")
    tl = analysis.get("time_labels", [])
    if not tc or not pn or len(tl) < 2:
        return {"comparison": []}
    mid = len(tl) // 2
    h1_labels, h2_labels = tl[:mid], tl[mid:]
    def sum_period(data, labels):
        total = 0
        for t in labels:
            td = data[data[tc].astype(str).str.strip().str.lower() == str(t).strip().lower()]
            total += float(td[pn].sum()) if len(td) > 0 else 0
        return round(total, 2)
    results = []
    if pc:
        for cat in analysis.get("category_values", {}).get(pc, []):
            sub = df[df[pc] == cat]
            h1 = sum_period(sub, h1_labels)
            h2 = sum_period(sub, h2_labels)
            change = round(((h2 - h1) / h1 * 100) if h1 > 0 else 0, 2)
            momentum = "Accelerating" if change > 10 else ("Decelerating" if change < -10 else "Stable")
            results.append({"category": str(cat), "period_1": h1, "period_2": h2,
                            "change_pct": change, "momentum": momentum})
    else:
        h1 = sum_period(df, h1_labels)
        h2 = sum_period(df, h2_labels)
        change = round(((h2 - h1) / h1 * 100) if h1 > 0 else 0, 2)
        results.append({"category": "Overall", "period_1": h1, "period_2": h2,
                        "change_pct": change, "momentum": "Accelerating" if change > 10 else ("Decelerating" if change < -10 else "Stable")})
    return {"comparison": results, "period_1_label": f"{tl[0]}–{tl[mid - 1]}",
            "period_2_label": f"{tl[mid]}–{tl[-1]}", "metric": pn}


# ═══════════════════════════════════════════════════
# MODULE 6: ANOMALY DETECTION
# ═══════════════════════════════════════════════════
def detect_anomalies(analysis, df):
    """Detect data anomalies — fully generic."""
    anomalies = []
    pc = analysis.get("primary_cat")
    pn = analysis.get("primary_num")
    if not pc or not pn:
        return anomalies

    cat_stats = analysis.get("category_stats", {}).get(pc, {})
    growth = analysis.get("growth_rates", {})

    for val, rates in growth.items():
        for rate in rates:
            if abs(rate) > 25:
                anomalies.append({
                    "type": "growth_spike" if rate > 0 else "growth_drop",
                    "product": str(val), "severity": "high" if abs(rate) > 40 else "medium",
                    "value": rate,
                    "message": f"{val} showed a {'spike' if rate > 0 else 'drop'} of {rate:.1f}% growth in {pn}",
                })

    for val, stats in cat_stats.items():
        for nc, ns in stats.items():
            std_val = ns.get("std", 0)
            mean_val = ns.get("mean", 1)
            cv = (std_val / mean_val * 100) if mean_val > 0 else 0
            if cv > 30:
                anomalies.append({
                    "type": "high_variance", "product": str(val), "severity": "low",
                    "value": cv, "message": f"{val} has high {nc} variability (CV: {cv:.1f}%)",
                })
    return anomalies


# ═══════════════════════════════════════════════════
# MODULE 6: EMAIL REPORTER
# ═══════════════════════════════════════════════════
def send_email(to_email, subject, html_body):
    """Alternative: Open default mail client (mailto) with pre-filled text."""
    import re
    import platform
    import urllib.parse
    import webbrowser
    
    try:
        # Save HTML locally as a backup
        safe_subject = re.sub(r'[^a-zA-Z0-9_\- ]', '', subject).strip().replace(' ', '_')
        filename = f"email_{safe_subject}.html"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_body)
            
        # Convert HTML to basic Plain Text for the email client body
        text_body = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', html_body)
        text_body = text_body.replace('</tr>', '\n').replace('</h1>', '\n\n').replace('</h3>', '\n').replace('</li>', '\n')
        text_body = re.sub(r'<[^>]+>', ' ', text_body)
        text_body = re.sub(r'[ \t]+', ' ', text_body)
        text_body = "\n".join(line.strip() for line in text_body.split('\n') if line.strip())
        
        final_body = (
            f"--- SYSTEM AUTO-GENERATED REPORT ---\n\n"
            f"{text_body}\n\n"
            f"--- END OF REPORT ---\n"
            f"(Rich HTML version safely compiled to: {filepath})"
        )
        
        # Prevent URL TOO LONG crash on windows (standard limit ~2048 chars)
        if len(final_body) > 1700:
            final_body = final_body[:1700] + "\n\n...[REPORT TRUNCATED DUE TO URL LENGTH LIMITS]..."
            
        # Spawn mail client. Omit 'to_email' so user can manually type receivers.
        mailto_url = f"mailto:?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(final_body)}"
        webbrowser.open(mailto_url)
            
        return True, "Mail client spawned successfully"
    except Exception as e:
        return False, str(e)



def generate_manager_report_html(analysis, predictions, anomalies, news_data):
    """Build a stylish HTML email report."""
    # Product prediction rows
    product_rows = ""
    for pred in predictions.get("product_predictions", []):
        tc = "#34d399" if pred.get("trend") == "increasing" else "#ef4444" if pred.get("trend") == "decreasing" else "#fbbf24"
        ti = "📈" if pred.get("trend") == "increasing" else "📉" if pred.get("trend") == "decreasing" else "➡️"
        ai = "🟢" if pred.get("action") == "increase_stock" else "🔴" if pred.get("action") == "decrease_stock" else "🟡"
        product_rows += f"""<tr>
            <td style="padding:12px;border-bottom:1px solid #1e293b;">{pred.get('product','')}</td>
            <td style="padding:12px;border-bottom:1px solid #1e293b;color:{tc};">{ti} {pred.get('trend','')}</td>
            <td style="padding:12px;border-bottom:1px solid #1e293b;">{pred.get('confidence',0)}%</td>
            <td style="padding:12px;border-bottom:1px solid #1e293b;color:{tc};">{pred.get('predicted_change_percent',0):+.1f}%</td>
            <td style="padding:12px;border-bottom:1px solid #1e293b;">{ai} {pred.get('action','').replace('_',' ').title()}</td>
        </tr>"""

    anomaly_items = "".join(
        f'<li style="margin:8px 0;color:{"#ef4444" if a["severity"]=="high" else "#fbbf24" if a["severity"]=="medium" else "#60a5fa"};">⚠️ {a["message"]}</li>'
        for a in anomalies[:5]
    )
    insight_items = "".join(f'<li style="margin:8px 0;">💡 {x}</li>' for x in predictions.get("key_insights", [])[:5])
    rec_items = "".join(f'<li style="margin:8px 0;">✅ {x}</li>' for x in predictions.get("recommendations", [])[:5])
    oc = "#34d399" if predictions.get("overall_outlook") == "bullish" else "#ef4444" if predictions.get("overall_outlook") == "bearish" else "#fbbf24"

    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="background:#0f172a;color:#e2e8f0;font-family:'Segoe UI',Arial,sans-serif;padding:30px;margin:0;">
<div style="max-width:800px;margin:0 auto;background:#1e293b;border-radius:16px;overflow:hidden;box-shadow:0 25px 50px rgba(0,0,0,.5);">
  <div style="background:linear-gradient(135deg,#6366f1,#8b5cf6,#ec4899);padding:40px 30px;text-align:center;">
    <h1 style="margin:0;font-size:28px;color:#fff;">📊 Sales Intelligence Report</h1>
    <p style="margin:10px 0 0;color:rgba(255,255,255,.85);font-size:14px;">Generated {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
    <p style="margin:5px 0 0;color:rgba(255,255,255,.7);font-size:12px;">NEXT CORE AI — Agentic Pipeline</p>
  </div>
  <div style="display:flex;padding:20px 30px;gap:15px;flex-wrap:wrap;">
    <div style="flex:1;min-width:150px;background:#0f172a;border-radius:12px;padding:20px;text-align:center;">
      <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;">{analysis.get('kpi_labels', {}).get('total_1', 'Total KPI 1')}</div>
      <div style="font-size:24px;font-weight:700;color:#6366f1;margin-top:5px;">${analysis.get('kpi_total_1', 0):,.0f}</div>
    </div>
    <div style="flex:1;min-width:150px;background:#0f172a;border-radius:12px;padding:20px;text-align:center;">
      <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;">{analysis.get('kpi_labels', {}).get('total_2', 'Total KPI 2')}</div>
      <div style="font-size:24px;font-weight:700;color:#34d399;margin-top:5px;">${analysis.get('kpi_total_2', 0):,.0f}</div>
    </div>
    <div style="flex:1;min-width:150px;background:#0f172a;border-radius:12px;padding:20px;text-align:center;">
      <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;">{analysis.get('kpi_labels', {}).get('ratio', 'Margin')}</div>
      <div style="font-size:24px;font-weight:700;color:#fbbf24;margin-top:5px;">{analysis.get('kpi_ratio', 0)}%</div>
    </div>
    <div style="flex:1;min-width:150px;background:#0f172a;border-radius:12px;padding:20px;text-align:center;">
      <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;">Outlook</div>
      <div style="font-size:24px;font-weight:700;color:{oc};margin-top:5px;">{predictions.get('overall_outlook','N/A').upper()}</div>
    </div>
  </div>
  <div style="padding:0 30px 20px;">
    <div style="background:#0f172a;border-radius:12px;padding:20px;border-left:4px solid #6366f1;">
      <h3 style="margin:0 0 10px;color:#6366f1;">🤖 AI Summary</h3>
      <p style="margin:0;line-height:1.6;color:#cbd5e1;">{predictions.get('summary','')}</p>
    </div>
  </div>
  <div style="padding:0 30px 20px;">
    <h3 style="color:#e2e8f0;margin-bottom:15px;">📈 Product Predictions</h3>
    <table style="width:100%;border-collapse:collapse;background:#0f172a;border-radius:12px;overflow:hidden;">
      <thead><tr style="background:#1e293b;">
        <th style="padding:14px 12px;text-align:left;color:#94a3b8;font-size:12px;text-transform:uppercase;">Product</th>
        <th style="padding:14px 12px;text-align:left;color:#94a3b8;font-size:12px;text-transform:uppercase;">Trend</th>
        <th style="padding:14px 12px;text-align:left;color:#94a3b8;font-size:12px;text-transform:uppercase;">Confidence</th>
        <th style="padding:14px 12px;text-align:left;color:#94a3b8;font-size:12px;text-transform:uppercase;">Change</th>
        <th style="padding:14px 12px;text-align:left;color:#94a3b8;font-size:12px;text-transform:uppercase;">Action</th>
      </tr></thead>
      <tbody>{product_rows}</tbody>
    </table>
  </div>
  {"" if not anomalies else f'<div style="padding:0 30px 20px;"><h3 style="color:#e2e8f0;margin-bottom:10px;">⚠️ Anomalies</h3><ul style="list-style:none;padding:15px 20px;background:#0f172a;border-radius:12px;">{anomaly_items}</ul></div>'}
  <div style="padding:0 30px 20px;"><h3 style="color:#e2e8f0;margin-bottom:10px;">💡 Key Insights</h3><ul style="list-style:none;padding:15px 20px;background:#0f172a;border-radius:12px;">{insight_items}</ul></div>
  <div style="padding:0 30px 20px;"><h3 style="color:#e2e8f0;margin-bottom:10px;">✅ Recommendations</h3><ul style="list-style:none;padding:15px 20px;background:#0f172a;border-radius:12px;">{rec_items}</ul></div>
  <div style="padding:20px 30px;text-align:center;border-top:1px solid #334155;">
    <p style="margin:0;font-size:12px;color:#64748b;">NEXT CORE AI Agentic Pipeline · Confidence {predictions.get('confidence',0)}% · {len(list(analysis.get('category_values', {}).values())[0]) if analysis.get('category_values') else 0} categories · {news_data.get('count',0)} news sources</p>
  </div>
</div></body></html>"""
    return html


def send_manager_report(analysis, predictions, anomalies, news_data):
    html = generate_manager_report_html(analysis, predictions, anomalies, news_data)
    subj = f"📊 Sales Intelligence Report — {datetime.now().strftime('%b %d, %Y')} | {predictions.get('overall_outlook','N/A').upper()}"
    return send_email(MANAGER_EMAIL, subj, html)


# ═══════════════════════════════════════════════════
# MODULE 7: SUPPLIER NOTIFIER
# ═══════════════════════════════════════════════════
def send_supplier_alerts(predictions):
    results = []
    for pred in predictions.get("product_predictions", []):
        action = pred.get("action", "maintain")
        product = pred.get("product", "Unknown")
        if action in ("increase_stock", "decrease_stock"):
            grad = "#34d399,#059669" if action == "increase_stock" else "#ef4444,#dc2626"
            label = "🟢 STOCK INCREASE" if action == "increase_stock" else "🔴 STOCK REDUCTION"
            html = f"""<html><body style="background:#0f172a;color:#e2e8f0;font-family:'Segoe UI',sans-serif;padding:30px;">
<div style="max-width:600px;margin:0 auto;background:#1e293b;border-radius:16px;overflow:hidden;">
  <div style="background:linear-gradient(135deg,{grad});padding:30px;text-align:center;">
    <h1 style="margin:0;color:#fff;">{label} ADVISORY</h1>
    <p style="color:rgba(255,255,255,.8);margin:10px 0 0;">Product: {product}</p>
  </div>
  <div style="padding:30px;">
    <p style="font-size:16px;line-height:1.6;">{pred.get('supplier_message', pred.get('reasoning','Stock adjustment needed.'))}</p>
    <div style="background:#0f172a;padding:20px;border-radius:12px;margin-top:20px;">
      <p style="margin:0;"><strong>Product:</strong> {product}</p>
      <p style="margin:8px 0 0;"><strong>Trend:</strong> {pred.get('trend','')}</p>
      <p style="margin:8px 0 0;"><strong>Predicted Change:</strong> {pred.get('predicted_change_percent',0):+.1f}%</p>
      <p style="margin:8px 0 0;"><strong>Confidence:</strong> {pred.get('confidence',0)}%</p>
      <p style="margin:8px 0 0;"><strong>Action:</strong> {action.replace('_',' ').title()}</p>
    </div>
    <p style="margin-top:20px;font-size:12px;color:#64748b;text-align:center;">NEXT CORE AI — {datetime.now().strftime('%B %d, %Y')}</p>
  </div>
</div></body></html>"""
            success, msg = send_email(SUPPLIER_EMAIL, f"{label}: {product} — Action Required", html)
            results.append({"product": product, "action": action, "email_sent": success, "message": msg})
    return results


# ═══════════════════════════════════════════════════
# MODULE 8: WHAT-IF SCENARIO ENGINE
# ═══════════════════════════════════════════════════
def run_what_if(analysis, scenario, news_data=None):
    news_summary = ""
    if news_data:
        for a in news_data.get("articles", [])[:10]:
            news_summary += f"- [{a.get('product','')}] {a.get('title')}: {a.get('description')}\n"

    prompt = f"""You are a business analyst. Given data, real market news, and a hypothetical scenario, predict the outcome using deep logic.

CURRENT DATA:
{json.dumps(analysis.get('category_stats', {}), indent=2)}

MARKET NEWS:
{news_summary if news_summary else 'No recent news available.'}

SCENARIO: {scenario}

Return ONLY JSON (no markdown/code fences):
{{
  "scenario": "{scenario}",
  "impact_summary": "2-3 sentences incorporating news factors",
  "product_impacts": [
    {{"product":"Category Value Name","sales_change_percent":number,"profit_change_percent":number,"explanation":"brief factor based evaluation"}}
  ],
  "overall_risk": "low/medium/high",
  "recommendation": "what to do"
}}"""
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "response_format": {"type": "json_object"}
            },
            timeout=20
        )
        data = resp.json()
        if "choices" not in data or len(data["choices"]) == 0:
            raise Exception(data.get("error", {}).get("message", "Unknown API Error"))
        text = data["choices"][0]["message"]["content"].strip()
        return json.loads(text)
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/upload", methods=["POST"])
def upload_csv():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "No file selected"}), 400
    filepath = os.path.join(UPLOAD_FOLDER, "current_data.csv")
    f.save(filepath)
    return jsonify({"success": True, "message": "File uploaded", "filename": f.filename})


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    filepath = os.path.join(UPLOAD_FOLDER, "current_data.csv")
    if not os.path.exists(filepath):
        filepath = "sales.csv"
    if not os.path.exists(filepath):
        return jsonify({"error": "No CSV file found"}), 404
    analysis, df = analyze_csv(filepath)
    charts = generate_chart_data(analysis, df)
    anomalies = detect_anomalies(analysis, df)
    return jsonify({"analysis": analysis, "charts": charts, "anomalies": anomalies})


@app.route("/api/news", methods=["GET"])
def api_news():
    filepath = os.path.join(UPLOAD_FOLDER, "current_data.csv")
    if not os.path.exists(filepath):
        filepath = "sales.csv"
    analysis, df = analyze_csv(filepath)
    pc = analysis.get("primary_cat")
    search_terms = list(analysis.get("category_values", {}).get(pc, []))[:5] if pc else ["business market"]
    return jsonify(fetch_market_news(search_terms))


@app.route("/api/predict", methods=["POST"])
def api_predict():
    filepath = os.path.join(UPLOAD_FOLDER, "current_data.csv")
    if not os.path.exists(filepath):
        filepath = "sales.csv"
    analysis, df = analyze_csv(filepath)
    pc = analysis.get("primary_cat")
    terms = list(analysis.get("category_values", {}).get(pc, []))[:5] if pc else ["business"]
    news = fetch_market_news(terms)
    return jsonify(predict_market(analysis, news))


@app.route("/api/supplier-alert", methods=["POST"])
def api_supplier_alert():
    data = request.get_json() or {}
    preds = data.get("predictions", pipeline_state.get("predictions", {}))
    if not preds:
        return jsonify({"error": "No predictions available — run the pipeline first."}), 400
    return jsonify({"results": send_supplier_alerts(preds)})


@app.route("/api/manager-report", methods=["POST"])
def api_manager_report():
    filepath = os.path.join(UPLOAD_FOLDER, "current_data.csv")
    if not os.path.exists(filepath):
        filepath = "sales.csv"
    analysis, df = analyze_csv(filepath)
    pc = analysis.get("primary_cat")
    terms = list(analysis.get("category_values", {}).get(pc, []))[:5] if pc else ["business"]
    news = fetch_market_news(terms)
    preds = predict_market(analysis, news)
    anomalies = detect_anomalies(analysis, df)
    ok, msg = send_manager_report(analysis, preds, anomalies, news)
    return jsonify({"success": ok, "message": msg})


@app.route("/api/what-if", methods=["POST"])
def api_what_if():
    data = request.get_json()
    scenario = data.get("scenario", "")
    if not scenario:
        return jsonify({"error": "No scenario provided"}), 400
    filepath = os.path.join(UPLOAD_FOLDER, "current_data.csv")
    if not os.path.exists(filepath):
        filepath = "sales.csv"
    analysis, _ = analyze_csv(filepath)
    news = pipeline_state.get("news", {})
    return jsonify(run_what_if(analysis, scenario, news))


# ═══════════════════════════════════════════════════
# MODULE 9: STRATEGIC ADVISOR (AI-powered)
# ═══════════════════════════════════════════════════
def strategic_advisor(analysis, df):
    """AI-powered strategic advisor — comprehensive business recommendations."""
    pc = analysis.get("primary_cat", "Category")
    pn = analysis.get("primary_num", "Value")
    sn = analysis.get("secondary_num", "")
    cat_stats = analysis.get("category_stats", {}).get(pc, {})
    growth = analysis.get("growth_rates", {})
    nc = analysis.get("numeric_cols", [])

    # Run DSS modules for context
    pareto = pareto_abc_analysis(analysis, df)
    forecast = statistical_forecast(analysis, df)
    dm = decision_matrix(analysis, df)
    risk = risk_scoring(analysis, df)
    hhi = concentration_index(analysis, df)
    sensitivity = sensitivity_analysis(analysis, df)
    period_comp = period_comparison(analysis, df)

    # Build comprehensive context
    pareto_summary = ""
    for cat, t in pareto.get("tiers", {}).items():
        pareto_summary += f"  - {cat}: Tier {t['tier']}, {t['pct']}% share, cumulative {t['cumulative_pct']}%\n"

    risk_summary = ""
    for r in risk.get("risks", []):
        risk_summary += f"  - {r['category']}: Risk={r['risk_score']}/100 ({r['risk_level']}), CV={r['cv_pct']}%, Share={r['share_pct']}%\n"

    dm_summary = ""
    for m in dm.get("matrix", []):
        dm_summary += f"  - #{m['rank']} {m['category']}: Score={m['weighted_total']}/100\n"

    period_summary = ""
    for c in period_comp.get("comparison", []):
        period_summary += f"  - {c['category']}: P1=${c['period_1']:,.0f} → P2=${c['period_2']:,.0f} ({c['change_pct']:+.1f}%, {c['momentum']})\n"

    forecast_summary = ""
    if forecast.get("trend"):
        forecast_summary = f"Trend: {forecast['trend']}, Slope: {forecast.get('slope',0)}"
        for f in forecast.get("forecast", []):
            forecast_summary += f", Next period: {f['value']} (CI: {f['lower']}–{f['upper']})"

    sens_summary = ""
    for s in sensitivity.get("sensitivities", []):
        sens_summary += f"  - {s['category']}: Share={s['share_pct']}%, 10% impact=±${s['impact_of_10pct_change']:,.0f}, CV={s['volatility_cv']:.1f}%\n"

    prompt = f"""You are a world-class strategic business advisor. Based on the comprehensive data analysis below, provide DETAILED, SPECIFIC, ACTIONABLE business intelligence.

=== DATA OVERVIEW ===
Dataset: {analysis['shape']['rows']} rows, {len(nc)} numeric columns
Primary Category ({pc}): {', '.join(str(x) for x in list(analysis.get('category_values', {}).get(pc, [])))}
Primary Metric ({pn}): Total = {analysis.get('kpi_total_1', 0):,.2f}
{f"Secondary Metric ({sn}): Total = {analysis.get('kpi_total_2', 0):,.2f}" if sn else ""}
Top {pc}: {analysis.get('kpi_top', 'N/A')}
Bottom {pc}: {analysis.get('kpi_bottom', 'N/A')}

=== PARETO / ABC TIERS ===
{pareto_summary}

=== DECISION MATRIX RANKING ===
{dm_summary}

=== RISK ASSESSMENT ===
{risk_summary}
HHI Concentration: {hhi.get('hhi', 0)} ({hhi.get('interpretation', '')})

=== PERIOD COMPARISON ===
{period_summary}

=== FORECAST ===
{forecast_summary}

=== SENSITIVITY ===
{sens_summary}

=== INSTRUCTIONS ===
Return ONLY a JSON object (no markdown, no code fences):
{{
  "immediate_actions": [
    {{"priority": "HIGH/MEDIUM/LOW", "action": "specific action to take right now", "category": "which category/area", "expected_impact": "what will happen", "timeline": "when to do it"}}
  ],
  "sales_growth_strategies": [
    {{"strategy": "specific strategy name", "description": "detailed description of how to increase sales", "target_categories": ["which categories"], "estimated_impact_pct": number, "effort_level": "low/medium/high", "timeline": "short-term/medium-term/long-term"}}
  ],
  "stock_recommendations": [
    {{"category": "category name", "current_status": "overstocked/understocked/optimal/at_risk", "action": "increase/decrease/maintain/urgent_reorder", "quantity_change_pct": number, "reasoning": "why", "reorder_urgency": "immediate/soon/scheduled/not_needed", "reorder_timeline": "when to reorder"}}
  ],
  "gap_analysis": [
    {{"area": "where we lag", "severity": "critical/moderate/minor", "current_state": "what's happening now", "desired_state": "where we should be", "action_plan": "how to close the gap", "affected_categories": ["categories"]}}
  ],
  "future_predictions": [
    {{"timeframe": "next_month/next_quarter/next_year", "prediction": "what will happen", "confidence": 0-100, "risk_factors": "what could go wrong", "opportunity": "what to capitalize on"}}
  ],
  "current_status_summary": {{
    "overall_health": "excellent/good/moderate/concerning/critical",
    "health_score": 0-100,
    "top_strength": "biggest strength",
    "top_weakness": "biggest weakness",
    "key_metric_status": "above_target/on_target/below_target",
    "diversification_status": "well_diversified/moderately_concentrated/highly_concentrated"
  }}
}}"""

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "response_format": {"type": "json_object"}
            },
            timeout=30
        )
        data = resp.json()
        if "choices" not in data or len(data["choices"]) == 0:
            raise Exception(data.get("error", {}).get("message", "Unknown API Error"))
        text = data["choices"][0]["message"]["content"].strip()
        return json.loads(text)
    except json.JSONDecodeError:
        return {"error": "AI response could not be parsed"}
    except Exception as e:
        return {"error": f"Strategic advisor failed: {e}"}


@app.route("/api/strategic-advisor", methods=["POST"])
def api_strategic_advisor():
    """AI-powered strategic business advisor."""
    filepath = os.path.join(UPLOAD_FOLDER, "current_data.csv")
    if not os.path.exists(filepath):
        filepath = "sales.csv"
    if not os.path.exists(filepath):
        return jsonify({"error": "No CSV file found"}), 404
    analysis, df = analyze_csv(filepath)
    return jsonify(strategic_advisor(analysis, df))


@app.route("/api/dss-analysis", methods=["POST"])
def api_dss_analysis():
    """Full DSS analysis — Pareto, Forecast, Decision Matrix, Risk, HHI, Sensitivity, Period Comparison."""
    filepath = os.path.join(UPLOAD_FOLDER, "current_data.csv")
    if not os.path.exists(filepath):
        filepath = "sales.csv"
    if not os.path.exists(filepath):
        return jsonify({"error": "No CSV file found"}), 404
    analysis, df = analyze_csv(filepath)
    return jsonify({
        "pareto": pareto_abc_analysis(analysis, df),
        "forecast": statistical_forecast(analysis, df),
        "decision_matrix": decision_matrix(analysis, df),
        "risk": risk_scoring(analysis, df),
        "concentration": concentration_index(analysis, df),
        "sensitivity": sensitivity_analysis(analysis, df),
        "period_comparison": period_comparison(analysis, df),
    })


@app.route("/api/run-pipeline", methods=["POST"])
def api_run_pipeline():
    """Full agentic pipeline — 7 autonomous steps."""
    global pipeline_state
    pipeline_state = {
        "status": "running", "steps": [], "current_step": 0, "total_steps": 8,
        "data": None, "charts": None, "news": None, "predictions": None,
        "anomalies": None, "dss": None, "report_sent": False, "supplier_alerted": False,
        "last_run": datetime.now().isoformat(),
    }

    try:
        # ── Step 1: Analyse CSV ──
        pipeline_state["steps"].append({"step": 1, "name": "Analyzing CSV Data", "status": "running", "icon": "📊"})
        pipeline_state["current_step"] = 1
        filepath = os.path.join(UPLOAD_FOLDER, "current_data.csv")
        if not os.path.exists(filepath):
            filepath = "sales.csv"
        analysis, df = analyze_csv(filepath)
        pipeline_state["data"] = analysis
        pc = analysis.get("primary_cat")
        n_cats = len(analysis.get("category_values", {}).get(pc, [])) if pc else 0
        pipeline_state["steps"][-1].update({"status": "completed", "result": f"Analysed {analysis['shape']['rows']} rows, {n_cats} categories"})

        # ── Step 2: Generate Charts ──
        pipeline_state["steps"].append({"step": 2, "name": "Generating 10 Charts", "status": "running", "icon": "📈"})
        pipeline_state["current_step"] = 2
        charts = generate_chart_data(analysis, df)
        pipeline_state["charts"] = charts
        pipeline_state["steps"][-1].update({"status": "completed", "result": f"Generated {len(charts)} chart datasets"})

        # ── Step 3: Anomaly Detection ──
        pipeline_state["steps"].append({"step": 3, "name": "Detecting Anomalies", "status": "running", "icon": "🔍"})
        pipeline_state["current_step"] = 3
        anomalies = detect_anomalies(analysis, df)
        pipeline_state["anomalies"] = anomalies
        pipeline_state["steps"][-1].update({"status": "completed", "result": f"Found {len(anomalies)} anomalies"})

        # ── Step 4: Fetch Market News ──
        pipeline_state["steps"].append({"step": 4, "name": "Fetching Market News", "status": "running", "icon": "📰"})
        pipeline_state["current_step"] = 4
        terms = list(analysis.get("category_values", {}).get(pc, []))[:5] if pc else ["business market"]
        news = fetch_market_news(terms)
        pipeline_state["news"] = news
        pipeline_state["steps"][-1].update({"status": "completed", "result": f"Fetched {news.get('count',0)} articles"})

        # ── Step 5: AI Predictions ──
        pipeline_state["steps"].append({"step": 5, "name": "Running AI Predictions", "status": "running", "icon": "🤖"})
        pipeline_state["current_step"] = 5
        preds = predict_market(analysis, news)
        pipeline_state["predictions"] = preds
        pipeline_state["steps"][-1].update({"status": "completed", "result": f"Outlook: {preds.get('overall_outlook','N/A').upper()} ({preds.get('confidence',0)}%)"})

        # ── Step 6: Email Manager Report ──
        pipeline_state["steps"].append({"step": 6, "name": "Emailing Manager Report", "status": "running", "icon": "📧"})
        pipeline_state["current_step"] = 6
        try:
            ok, msg = send_manager_report(analysis, preds, anomalies, news)
            pipeline_state["report_sent"] = ok
            pipeline_state["steps"][-1].update({"status": "completed" if ok else "warning", "result": msg})
        except Exception as e:
            pipeline_state["steps"][-1].update({"status": "warning", "result": f"Email error: {e}"})

        # ── Step 7: Supplier Alerts ──
        pipeline_state["steps"].append({"step": 7, "name": "Sending Supplier Alerts", "status": "running", "icon": "📦"})
        pipeline_state["current_step"] = 7
        try:
            sr = send_supplier_alerts(preds)
            pipeline_state["supplier_alerted"] = len(sr) > 0
            pipeline_state["steps"][-1].update({"status": "completed", "result": f"Sent {len(sr)} alerts"})
        except Exception as e:
            pipeline_state["steps"][-1].update({"status": "warning", "result": f"Alert error: {e}"})

        # ── Step 8: DSS Analysis ──
        pipeline_state["steps"].append({"step": 8, "name": "DSS Analytics Engine", "status": "running", "icon": "🎯"})
        pipeline_state["current_step"] = 8
        try:
            dss = {
                "pareto": pareto_abc_analysis(analysis, df),
                "forecast": statistical_forecast(analysis, df),
                "decision_matrix": decision_matrix(analysis, df),
                "risk": risk_scoring(analysis, df),
                "concentration": concentration_index(analysis, df),
                "sensitivity": sensitivity_analysis(analysis, df),
                "period_comparison": period_comparison(analysis, df),
            }
            pipeline_state["dss"] = dss
            n_risks = len([r for r in dss.get('risk', {}).get('risks', []) if r['risk_level'] != 'LOW'])
            pipeline_state["steps"][-1].update({"status": "completed", "result": f"7 DSS modules · {n_risks} risks flagged · HHI {dss.get('concentration',{}).get('hhi',0)}"})
        except Exception as e:
            pipeline_state["steps"][-1].update({"status": "warning", "result": f"DSS error: {e}"})

        pipeline_state["status"] = "completed"
        return jsonify(pipeline_state)

    except Exception as e:
        pipeline_state["status"] = "failed"
        pipeline_state["error"] = str(e)
        return jsonify(pipeline_state), 500


@app.route("/api/pipeline-status", methods=["GET"])
def api_pipeline_status():
    return jsonify(pipeline_state)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
