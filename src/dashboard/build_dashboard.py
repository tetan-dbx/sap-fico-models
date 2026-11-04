#!/usr/bin/env python3
"""Generate the CFO 'Financial Cockpit' AI/BI dashboard (.lvdash.json).

Sources: ONLY the four semantic_* metric views (MEASURE() + GROUP BY). View names are
written UNQUALIFIED; the bundle sets the default catalog/schema of every dataset at
deploy time (`dataset_catalog` / `dataset_schema` in resources/fico_dashboard.yml), so
the generated JSON is environment-independent.

Additive measures re-aggregate with SUM at the widget level; non-additive ones (DSO/DPO,
forecast accuracy, entry lag) are shown at their display grain (disaggregated).

Conventions:
  * every numeric encoding carries a `format` (currency / count / days / percent)
  * a top-level uiSettings.theme (Inter font, brand palette, rounded cards)
  * a bounded default time window (dense ~4-year series, capped forecast horizon)
  * AP payables shown as positive magnitudes; forecast accuracy stored as a fraction

Branding, theme and window live in CONFIG (overridable from the command line) so the
dashboard re-skins per company.

Usage:
  python build_dashboard.py --custom        # full build incl. custom Vega-Lite (gauge/radial)
  python build_dashboard.py                 # native widgets only
  python build_dashboard.py --custom --customer "Contoso" --wordmark "CONTOSO" --currency EUR
"""
import argparse, base64, json, os

HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
ap.add_argument("--custom", action="store_true", help="include custom Vega-Lite widgets (Public Preview)")
ap.add_argument("--customer", default="Contoso", help="company name shown in the dashboard header")
ap.add_argument("--wordmark", default=None, help="header wordmark text (default: upper-cased --customer)")
ap.add_argument("--currency", default="EUR", help="ISO currency code used to format money")
ap.add_argument("--logo", default=os.path.join(HERE, "assets", "logo.png"),
                help="optional PNG logo (<=37 KB) for the unwired Vega image-mark helper")
ap.add_argument("--output", default=os.path.join(HERE, "fico_cockpit.lvdash.json"), help="output .lvdash.json path")
ARGS = ap.parse_args()
USE_CUSTOM = ARGS.custom

# ---------------------------------------------------------------- branding / theme / window
CONFIG = {
    "customer": ARGS.customer,
    "wordmark": ARGS.wordmark or ARGS.customer.upper(),  # branded header text
    "title": "Financial Cockpit",
    "subtitle": "SAP FICO — General Ledger · Controlling · Cash & Liquidity · Working Capital",
    "logo_path": ARGS.logo,        # optional; brand assets stay local (src/dashboard/assets/ is gitignored)
    "currency": ARGS.currency,     # cash-flow group currency in the SAP sample data is predominantly EUR
    "report_start": "2022-01-01",  # floor for every period series (kills pre-2022 flatline)
    "forecast_cap": "2026-12-31",  # cap cash-flow forecast horizon (~12m past last actual)
    "theme": {
        "canvasBackgroundColor": {"light": "#FAFAFB", "dark": "#1F272D"},
        "widgetBackgroundColor": {"light": "#FFFFFF", "dark": "#11171C"},
        "widgetBorderColor": {"light": "#FFFFFF", "dark": "#11171C"},
        "fontColor": {"light": "#000000", "dark": "#E8ECF0"},
        "selectionColor": {"light": "#2272B4", "dark": "#8ACAFF"},
        "visualizationColors": ["#077A9D", "#FFAB00", "#00A972", "#FF3621", "#8BCAE7",
                                 "#AB4057", "#99DDB4", "#FCA4A1", "#919191", "#BF7080", "#077A9D"],
        "widgetHeaderAlignment": "CENTER", "fontFamily": "Inter",
        "widgetPadding": 12, "widgetMargin": 8, "widgetCornerRadius": 8, "widgetShadow": 10,
    },
}
RS, FC, CUR = CONFIG["report_start"], CONFIG["forecast_cap"], CONFIG["currency"]

def logo_data_uri():
    with open(CONFIG["logo_path"], "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()

# ---------------------------------------------------------------- number formats
FMT_MONEY = {"type": "number-currency", "abbreviation": "compact", "currencyCode": CUR,
             "decimalPlaces": {"type": "exact", "places": 2}}
FMT_COUNT = {"type": "number-plain", "abbreviation": "compact", "decimalPlaces": {"type": "exact", "places": 2}}
FMT_DAYS = {"type": "number-plain", "abbreviation": "none", "decimalPlaces": {"type": "exact", "places": 1}}
FMT_PCT = {"type": "number-percent"}

# ---------------------------------------------------------------- datasets (all tested)
GL, CC, CF, OI = ("semantic_gl_journal_metrics", "semantic_cost_center_metrics",
                  "semantic_cash_flow_metrics", "semantic_open_items_ar_ap_metrics")
D = {
"gl_month": f"""SELECT CAST(`Posting Year` AS INT) AS fiscal_year, `Company` AS company, `Posting Month` AS month,
 `Account Type` AS account_type,
 MEASURE(`Net Movement (Local)`) AS net_movement, MEASURE(`Debit (Local)`) AS debit,
 MEASURE(`Credit (Local)`) AS credit, MEASURE(`Journal Line Count`) AS line_count,
 MEASURE(`Reversal Line Count`) AS reversal_lines, MEASURE(`Accounting Document Count`) AS doc_count,
 MEASURE(`YTD Net Movement (Local)`) AS ytd_net
 FROM {GL} WHERE `Posting Date` >= DATE'{RS}' GROUP BY 1,2,3,4""",
"gl_account": f"""SELECT CAST(`Posting Year` AS INT) AS fiscal_year, `Company` AS company, `G/L Account` AS gl_account,
 `Account Type` AS account_type, MEASURE(`Net Movement (Local)`) AS net_movement,
 MEASURE(`Debit (Local)`) AS debit, MEASURE(`Credit (Local)`) AS credit
 FROM {GL} WHERE `Posting Date` >= DATE'{RS}' GROUP BY 1,2,3,4""",
"gl_lag": f"""SELECT CAST(`Posting Year` AS INT) AS fiscal_year, `Company` AS company, `Posting Month` AS month,
 MEASURE(`Average Entry Lag Days`) AS avg_entry_lag
 FROM {GL} WHERE `Posting Date` >= DATE'{RS}' GROUP BY 1,2,3""",
"gl_debit_kpi": f"""SELECT CAST(`Posting Year` AS INT) AS fiscal_year, `Company` AS company,
 MEASURE(`Debit (Local)`) AS debit FROM {GL} WHERE `Posting Date` >= DATE'{RS}' GROUP BY 1,2""",
"cf_month": f"""SELECT CAST(year(`Posting Date`) AS INT) AS fiscal_year, `Company` AS company, `Flow Month` AS month,
 `Scenario` AS scenario, MEASURE(`Net Cash Flow (Local)`) AS net_cash,
 MEASURE(`Cash Inflow (Local)`) AS cash_in, MEASURE(`Cash Outflow (Local)`) AS cash_out,
 MEASURE(`Flow Count`) AS flow_count
 FROM {CF} WHERE `Flow Month` >= DATE'{RS}' AND `Flow Month` <= DATE'{FC}' AND `Posting Date` IS NOT NULL GROUP BY 1,2,3,4""",
"cf_ytd_actual": f"""SELECT CAST(year(`Posting Date`) AS INT) AS fiscal_year, `Company` AS company, `Flow Month` AS month,
 MEASURE(`YTD Net Cash Flow (Local)`) AS ytd_cash
 FROM {CF} WHERE `Scenario`='actual' AND `Flow Month` >= DATE'{RS}' AND `Flow Month` <= DATE'{FC}' AND `Posting Date` IS NOT NULL GROUP BY 1,2,3""",
"cf_accuracy": f"""SELECT fiscal_year, month, actual, forecast, variance, variance_pct, accuracy_pct / 100 AS accuracy_frac FROM (
 SELECT CAST(year(`Posting Date`) AS INT) AS fiscal_year, `Flow Month` AS month,
  MEASURE(`Actual Net Cash Flow`) AS actual, MEASURE(`Forecast Net Cash Flow`) AS forecast,
  MEASURE(`Forecast Variance`) AS variance, MEASURE(`Forecast Variance %`) AS variance_pct,
  MEASURE(`Forecast Accuracy %`) AS accuracy_pct
 FROM {CF} WHERE `Flow Month` >= DATE'{RS}' AND `Flow Month` <= DATE'{FC}' AND `Posting Date` IS NOT NULL GROUP BY 1,2)
 WHERE actual IS NOT NULL AND actual <> 0""",
"cf_actual_kpi": f"""SELECT CAST(year(`Posting Date`) AS INT) AS fiscal_year, `Company` AS company,
 MEASURE(`Net Cash Flow (Local)`) AS net_cash
 FROM {CF} WHERE `Scenario`='actual' AND `Flow Month` >= DATE'{RS}' AND `Flow Month` <= DATE'{FC}' AND `Posting Date` IS NOT NULL GROUP BY 1,2""",
"cc_hier": f"""SELECT CAST(`Posting Year` AS INT) AS fiscal_year, `Company` AS company,
 `Hierarchy Level 1` AS hier_l1, `Hierarchy Level 2` AS hier_l2,
 MEASURE(`Actual Spend (Local)`) AS spend, MEASURE(`Line Count`) AS line_count
 FROM {CC} WHERE `Hierarchy Level 1` IS NOT NULL AND `Posting Month` >= DATE'{RS}' GROUP BY 1,2,3,4""",
"cc_top": f"""SELECT CAST(`Posting Year` AS INT) AS fiscal_year, `Company` AS company, `Cost Center` AS cost_center,
 `Cost Center Name` AS cost_center_name, `Department` AS department,
 MEASURE(`Actual Spend (Local)`) AS spend
 FROM {CC} WHERE `Posting Month` >= DATE'{RS}' GROUP BY 1,2,3,4,5""",
"cc_ytd": f"""SELECT CAST(`Posting Year` AS INT) AS fiscal_year, `Company` AS company, `Posting Month` AS month,
 MEASURE(`YTD Spend (Local)`) AS ytd_spend, MEASURE(`Actual Spend (Local)`) AS spend
 FROM {CC} WHERE `Posting Month` >= DATE'{RS}' GROUP BY 1,2,3""",
# AR/AP amounts: ABS so AP payables read as positive magnitudes (AR already positive, unchanged).
"oi_aging": f"""SELECT fiscal_year, company, ar_ap, aging_bucket,
 ABS(open_amount) AS open_amount, ABS(overdue_amount) AS overdue_amount, open_items FROM (
 SELECT CAST(year(`Posting Date`) AS INT) AS fiscal_year, `Company` AS company, `AR / AP` AS ar_ap,
  `Aging Bucket` AS aging_bucket, MEASURE(`Open Amount`) AS open_amount,
  MEASURE(`Overdue Amount`) AS overdue_amount, MEASURE(`Open Item Count`) AS open_items
 FROM {OI} WHERE `Posting Date` >= DATE'{RS}' GROUP BY 1,2,3,4)""",
"oi_party": f"""SELECT fiscal_year, company, ar_ap, party, ABS(open_amount) AS open_amount FROM (
 SELECT CAST(year(`Posting Date`) AS INT) AS fiscal_year, `Company` AS company, `AR / AP` AS ar_ap,
  COALESCE(`Supplier`, `Customer`) AS party, MEASURE(`Open Amount`) AS open_amount
 FROM {OI} WHERE `Posting Date` >= DATE'{RS}' GROUP BY 1,2,3,4)""",
"oi_dsodpo": f"""SELECT `AR / AP` AS ar_ap, MEASURE(`DSO / DPO (Amount-Weighted)`) AS avg_days
 FROM {OI} WHERE `Posting Date` >= DATE'{RS}' GROUP BY 1""",
"kpi_dso": f"""SELECT MEASURE(`DSO / DPO (Amount-Weighted)`) AS dso
 FROM {OI} WHERE `AR / AP`='AR' AND `Posting Date` >= DATE'{RS}'""",
"kpi_dpo": f"""SELECT MEASURE(`DSO / DPO (Amount-Weighted)`) AS dpo
 FROM {OI} WHERE `AR / AP`='AP' AND `Posting Date` >= DATE'{RS}'""",
"kpi_open_ar": f"""SELECT CAST(year(`Posting Date`) AS INT) AS fiscal_year, `Company` AS company,
 MEASURE(`Open Amount`) AS open_amount FROM {OI} WHERE `AR / AP`='AR' AND `Posting Date` >= DATE'{RS}' GROUP BY 1,2""",
"kpi_open_ap": f"""SELECT fiscal_year, company, ABS(open_amount) AS open_amount FROM (
 SELECT CAST(year(`Posting Date`) AS INT) AS fiscal_year, `Company` AS company,
  MEASURE(`Open Amount`) AS open_amount FROM {OI} WHERE `AR / AP`='AP' AND `Posting Date` >= DATE'{RS}' GROUP BY 1,2)""",
}
CUSTOM_D = {
"gauge_clear": f"SELECT MEASURE(`Cleared Item Count`) AS cleared, MEASURE(`Item Count`) AS total FROM {OI} WHERE `Posting Date` >= DATE'{RS}'",
}

# datasets carrying each cross-filterable dimension (so global/page filters span all of them)
COMPANY_DS = ["gl_month", "gl_account", "gl_lag", "gl_debit_kpi", "cf_month", "cf_ytd_actual",
              "cf_actual_kpi", "cc_hier", "cc_top", "cc_ytd", "oi_aging", "oi_party", "kpi_open_ar", "kpi_open_ap"]
YEAR_DS = COMPANY_DS + ["cf_accuracy"]
MONTH_DS = ["gl_month", "gl_lag", "cf_month", "cf_ytd_actual", "cf_accuracy", "cc_ytd"]

# ---------------------------------------------------------------- widget builders
def q(ds, fields, disagg):
    return [{"name": "main_query", "query": {"datasetName": ds, "fields": fields, "disaggregated": disagg}}]

def text(name, x, y, w, h, md):
    return {"widget": {"name": name, "multilineTextboxSpec": {"lines": [md]}},
            "position": {"x": x, "y": y, "width": w, "height": h}}

def counter(name, ds, fname, expr, disagg, title, x, y, w=2, h=3, fmt=None):
    val = {"fieldName": fname, "displayName": title}
    if fmt: val["format"] = fmt
    return {"widget": {"name": name, "queries": q(ds, [{"name": fname, "expression": expr}], disagg),
            "spec": {"version": 2, "widgetType": "counter",
                     "encodings": {"value": val}, "frame": {"showTitle": True, "title": title}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}

def _yenc(yfields, fmt):
    e = ({"scale": {"type": "quantitative"}, "fields": [{"fieldName": n, "displayName": d} for n, _, d in yfields]}
         if len(yfields) > 1 else
         {"fieldName": yfields[0][0], "scale": {"type": "quantitative"}, "displayName": yfields[0][2]})
    if fmt: e["format"] = fmt
    return e

def bar(name, ds, xf, xexpr, yfields, title, x, y, w, h, xtype="categorical",
        color=None, colorexpr=None, grouped=False, disagg=False, fmt=None):
    fields = [{"name": xf, "expression": xexpr}] + [{"name": n, "expression": e} for n, e, _ in yfields]
    enc = {"x": {"fieldName": xf, "scale": {"type": xtype}, "displayName": xf}, "y": _yenc(yfields, fmt)}
    if color:
        fields.append({"name": color, "expression": colorexpr})
        enc["color"] = {"fieldName": color, "scale": {"type": "categorical"}, "displayName": color}
    spec = {"version": 3, "widgetType": "bar", "encodings": enc, "frame": {"showTitle": True, "title": title}}
    if grouped: spec["mark"] = {"layout": "group"}
    return {"widget": {"name": name, "queries": q(ds, fields, disagg), "spec": spec},
            "position": {"x": x, "y": y, "width": w, "height": h}}

def line(name, ds, xf, xexpr, yfields, title, x, y, w, h, xtype="temporal",
         color=None, colorexpr=None, disagg=False, fmt=None):
    fields = [{"name": xf, "expression": xexpr}] + [{"name": n, "expression": e} for n, e, _ in yfields]
    enc = {"x": {"fieldName": xf, "scale": {"type": xtype}, "displayName": xf}, "y": _yenc(yfields, fmt)}
    if color:
        fields.append({"name": color, "expression": colorexpr})
        enc["color"] = {"fieldName": color, "scale": {"type": "categorical"}, "displayName": color}
    return {"widget": {"name": name, "queries": q(ds, fields, disagg),
            "spec": {"version": 3, "widgetType": "line", "encodings": enc,
                     "frame": {"showTitle": True, "title": title}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}

def pie(name, ds, cat, catexpr, val, valexpr, title, x, y, w, h, disagg=False, fmt=None):
    ang = {"fieldName": val, "scale": {"type": "quantitative"}, "displayName": val}
    if fmt: ang["format"] = fmt
    return {"widget": {"name": name, "queries": q(ds, [{"name": cat, "expression": catexpr},
            {"name": val, "expression": valexpr}], disagg),
            "spec": {"version": 3, "widgetType": "pie",
                     "encodings": {"angle": ang,
                                   "color": {"fieldName": cat, "scale": {"type": "categorical"}, "displayName": cat}},
                     "frame": {"showTitle": True, "title": title}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}

def table(name, ds, cols, title, x, y, w, h, disagg=True):
    """cols: list of (name, expr, display[, fmt])."""
    fields = [{"name": c[0], "expression": c[1]} for c in cols]
    columns = []
    for c in cols:
        col = {"fieldName": c[0], "displayName": c[2]}
        if len(c) > 3 and c[3]:
            col["format"] = c[3]
        columns.append(col)
    return {"widget": {"name": name, "queries": q(ds, fields, disagg),
            "spec": {"version": 2, "widgetType": "table", "encodings": {"columns": columns},
                     "frame": {"showTitle": True, "title": title}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}

def filter_widget(name, field, ds_list, title, x, y, w=2, h=2, wtype="filter-multi-select"):
    """A filter linked to `field` across every dataset in ds_list (spans all their widgets)."""
    queries, enc_fields = [], []
    for ds in ds_list:
        qn = f"{field}__{ds}"
        queries.append({"name": qn, "query": {"datasetName": ds,
                        "fields": [{"name": field, "expression": f"`{field}`"}], "disaggregated": False}})
        enc_fields.append({"fieldName": field, "displayName": title, "queryName": qn})
    return {"widget": {"name": name, "queries": queries,
            "spec": {"version": 2, "widgetType": wtype, "encodings": {"fields": enc_fields},
                     "frame": {"showTitle": True, "title": title}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}

# ---------------------------------------------------------------- custom Vega-Lite (Public Preview)
def custom_vega(name, ds, fields, vega_spec, title, x, y, w, h):
    fld = [{"name": n, "expression": e} for n, e in fields]
    return {"widget": {"name": name,
            "queries": [{"name": "main_query", "query": {"datasetName": ds, "fields": fld}}],
            "spec": {"jsonSpec": {"type": "vega-lite", "spec": json.dumps(vega_spec)}},
            "version": 1, "widgetType": "custom-vega-viz",
            "encodings": {"fields": [{"fieldName": n} for n, _ in fields]},
            "data": {"queryName": "main_query"},
            "frame": {"title": title, "showTitle": True}},
            "position": {"x": x, "y": y, "width": w, "height": h}}

def gauge_spec():
    p = CONFIG["theme"]["visualizationColors"]
    return {"$schema": "https://vega.github.io/schema/vega-lite/v6.json", "width": "container", "height": "container",
            "data": {"name": "databricks_query"},
            "config": {"autosize": {"type": "fit", "contains": "padding"}, "font": "Inter"},
            "params": [{"name": "arc_size", "expr": "220"},
                       {"name": "ring_max", "expr": "min(width, height) / 2 - 16"},
                       {"name": "ring_width", "expr": "max(12, (min(width, height) / 2) * 0.14)"}],
            "transform": [
                {"as": "ratio", "calculate": "datum['$valueField'] / datum['$totalField']"},
                {"as": "_s", "calculate": "-2 * PI * (arc_size/2) / 360"},
                {"as": "_e", "calculate": "2 * PI * (arc_size/2) / 360"},
                {"as": "_re", "calculate": "datum['_s'] + (datum['_e'] - datum['_s']) * datum['ratio']"}],
            "layer": [
                {"mark": {"type": "arc", "color": "#e5e7eb", "theta": {"expr": "datum['_s']"},
                          "theta2": {"expr": "datum['_e']"}, "radius": {"expr": "ring_max"},
                          "radius2": {"expr": "ring_max - ring_width"}, "cornerRadius": 10}},
                {"mark": {"type": "arc", "theta": {"expr": "datum['_s']"}, "theta2": {"expr": "datum['_re']"},
                          "radius": {"expr": "ring_max"}, "radius2": {"expr": "ring_max - ring_width"}, "cornerRadius": 10},
                 "encoding": {"color": {"value": p[2],
                              "condition": [{"test": "datum['ratio'] < 0.33", "value": p[3]},
                                            {"test": "datum['ratio'] < 0.66", "value": p[1]}]},
                              "tooltip": [{"field": "$valueField", "type": "quantitative", "title": "Cleared"},
                                          {"field": "$totalField", "type": "quantitative", "title": "Total"}]}},
                {"mark": {"type": "text", "fontSize": 34, "fontWeight": "bold", "dy": 2},
                 "encoding": {"text": {"field": "ratio", "type": "quantitative", "format": ".0%"}}}]}

def radial_spec():
    return {"$schema": "https://vega.github.io/schema/vega-lite/v6.json", "width": "container", "height": "container",
            "data": {"name": "databricks_query"},
            "config": {"autosize": {"type": "fit", "contains": "padding"}, "font": "Inter",
                       "range": {"category": CONFIG["theme"]["visualizationColors"]}},
            "params": [{"name": "databricks_mark_selection", "select": {"type": "point", "fields": ["$colorField"]}}],
            "transform": [{"aggregate": [{"op": "sum", "field": "$valueField", "as": "total"}], "groupby": ["$colorField"]}],
            "layer": [{"mark": {"type": "arc", "innerRadius": 20, "stroke": "#fff"}}],
            "encoding": {
                "theta": {"field": "total", "type": "quantitative", "stack": True, "sort": "descending"},
                "radius": {"field": "total", "scale": {"type": "sqrt", "zero": True}},
                "color": {"field": "$colorField", "type": "nominal", "title": "Hierarchy L1",
                          "sort": {"field": "total", "order": "descending"}, "legend": {"orient": "right"}},
                "tooltip": [{"field": "$colorField", "type": "nominal", "title": "Hierarchy L1"},
                            {"field": "total", "type": "quantitative", "title": "Spend", "format": ",.0f"}]},
            "view": {"stroke": None}}

def logo_spec():
    # UNWIRED / OPTIONAL: Vega image-mark logos render unreliably in the current AI/BI custom-viz
    # Preview (intermittent "Visualization has no fields"), so the dashboard uses a markdown wordmark
    # header instead (see overview()). This helper (and --logo) is kept for future use if/when
    # image marks stabilize.
    return {"$schema": "https://vega.github.io/schema/vega-lite/v5.json", "width": "container", "height": "container",
            "data": {"name": "databricks_query"},
            "config": {"autosize": {"type": "fit", "contains": "padding"}, "view": {"stroke": None}, "background": "transparent"},
            "mark": {"type": "image", "url": logo_data_uri(), "aspect": True, "align": "center", "baseline": "middle"},
            # `anchor` is bound via the detail channel so the custom-viz framework sees >=1 field; the image renders regardless.
            "encoding": {"x": {"value": {"expr": "width/2"}}, "y": {"value": {"expr": "height/2"}},
                         "detail": {"field": "anchor", "type": "nominal"}}}

# ---------------------------------------------------------------- pages
def overview():
    # Branded header via markdown text widgets (always render, need no fields/spec) — a reliable
    # stand-in for a logo image. Vega image-mark logos are unreliable in the current Preview.
    L = [text("ov_brand", 0, 0, 2, 1, f"# {CONFIG['wordmark']}"),
         text("ov_title", 2, 0, 4, 1, f"## {CONFIG['customer']} · {CONFIG['title']}"),
         text("ov_sub", 0, 1, 6, 1, f"{CONFIG['subtitle']}  ·  Window from {RS[:7]} (forecast capped {FC[:7]})"),
         counter("kpi_debit", "gl_debit_kpi", "sum(debit)", "SUM(`debit`)", False, "GL Debit Postings", 0, 2, fmt=FMT_MONEY),
         counter("kpi_cash", "cf_actual_kpi", "sum(net_cash)", "SUM(`net_cash`)", False, "Net Cash Flow (Actual)", 2, 2, fmt=FMT_MONEY),
         counter("kpi_ar", "kpi_open_ar", "sum(open_amount)", "SUM(`open_amount`)", False, "Open Receivables", 4, 2, fmt=FMT_MONEY),
         counter("kpi_ap", "kpi_open_ap", "sum(open_amount)", "SUM(`open_amount`)", False, "Open Payables", 0, 5, fmt=FMT_MONEY),
         counter("kpi_dso", "kpi_dso", "dso", "`dso`", True, "DSO (days)", 2, 5, fmt=FMT_DAYS),
         counter("kpi_dpo", "kpi_dpo", "dpo", "`dpo`", True, "DPO (days)", 4, 5, fmt=FMT_DAYS),
         text("ov_h1", 0, 8, 6, 1, "### Cash flow — actual vs forecast"),
         line("ov_cash_trend", "cf_month", "month", "`month`",
              [("sum(net_cash)", "SUM(`net_cash`)", "Net Cash Flow")], "Net Cash Flow by Month", 0, 9, 4, 6,
              color="scenario", colorexpr="`scenario`", fmt=FMT_MONEY),
         bar("ov_net_by_type", "gl_month", "account_type", "`account_type`",
             [("sum(net_movement)", "SUM(`net_movement`)", "Net Movement")],
             "GL Net Movement by Account Type", 4, 9, 2, 6, fmt=FMT_MONEY)]
    return {"name": "overview", "displayName": "Executive Overview", "pageType": "PAGE_TYPE_CANVAS", "layout": L}

def gl_page():
    L = [text("gl_title", 0, 0, 4, 1, "## General Ledger / P&L"),
         filter_widget("gl_flt_type", "account_type", ["gl_month", "gl_account"], "Account Type", 4, 0, 2, 2),
         counter("gl_docs", "gl_month", "sum(doc_count)", "SUM(`doc_count`)", False, "Accounting Documents", 0, 2, fmt=FMT_COUNT),
         counter("gl_lines", "gl_month", "sum(line_count)", "SUM(`line_count`)", False, "Journal Lines", 2, 2, fmt=FMT_COUNT),
         counter("gl_rev", "gl_month", "sum(reversal_lines)", "SUM(`reversal_lines`)", False, "Reversal Lines", 4, 2, fmt=FMT_COUNT),
         bar("gl_dc_month", "gl_month", "month", "`month`",
             [("sum(debit)", "SUM(`debit`)", "Debit"), ("sum(credit)", "SUM(`credit`)", "Credit")],
             "Debit vs Credit by Month", 0, 5, 3, 6, xtype="temporal", grouped=True, fmt=FMT_MONEY),
         line("gl_ytd", "gl_month", "month", "`month`",
              [("sum(ytd_net)", "SUM(`ytd_net`)", "YTD Net Movement")],
              "YTD Net Movement (cumulative)", 3, 5, 3, 6, xtype="temporal", fmt=FMT_MONEY),
         line("gl_lag_trend", "gl_lag", "month", "`month`",
              [("avg_entry_lag", "`avg_entry_lag`", "Avg Entry Lag (days)")],
              "Posting Lag — Avg Entry Lag Days", 0, 11, 3, 5, xtype="temporal", disagg=True, fmt=FMT_DAYS),
         table("gl_top_acct", "gl_account",
               [("gl_account", "`gl_account`", "G/L Account"), ("account_type", "`account_type`", "Type"),
                ("net_movement", "`net_movement`", "Net Movement", FMT_MONEY), ("debit", "`debit`", "Debit", FMT_MONEY),
                ("credit", "`credit`", "Credit", FMT_MONEY)], "G/L Accounts", 3, 11, 3, 5, disagg=True)]
    return {"name": "gl", "displayName": "General Ledger / P&L", "pageType": "PAGE_TYPE_CANVAS", "layout": L}

def cc_page():
    L = [text("cc_title", 0, 0, 4, 1, "## Cost Center / Controlling"),
         filter_widget("cc_flt_hier", "hier_l1", ["cc_hier"], "Hierarchy L1", 4, 0, 2, 2),
         bar("cc_hier_bar", "cc_hier", "hier_l1", "`hier_l1`",
             [("sum(spend)", "SUM(`spend`)", "Spend")], "Spend by Hierarchy Level 1", 0, 2, 3, 6, fmt=FMT_MONEY),
         bar("cc_dept_bar", "cc_top", "department", "`department`",
             [("sum(spend)", "SUM(`spend`)", "Spend")], "Spend by Department", 3, 2, 3, 6, fmt=FMT_MONEY),
         line("cc_ytd_line", "cc_ytd", "month", "`month`",
              [("sum(ytd_spend)", "SUM(`ytd_spend`)", "YTD Spend")], "YTD Cost-Center Spend", 0, 8, 3, 6, xtype="temporal", fmt=FMT_MONEY),
         table("cc_top_tbl", "cc_top",
               [("cost_center", "`cost_center`", "Cost Center"), ("cost_center_name", "`cost_center_name`", "Name"),
                ("department", "`department`", "Department"), ("spend", "`spend`", "Spend", FMT_MONEY)],
               "Top Cost Centers", 3, 8, 3, 6, disagg=True)]
    return {"name": "cost_center", "displayName": "Cost Center / Controlling", "pageType": "PAGE_TYPE_CANVAS", "layout": L}

def cash_page():
    # Forecast is shown the way FP&A/treasury reports it: signed variance (actual - forecast) is the
    # headline, with accuracy floored at 0% as a bounded companion (a >100% miss reads 0%, never negative).
    L = [text("cf_title", 0, 0, 4, 1, "## Cash & Liquidity"),
         filter_widget("cf_flt_scn", "scenario", ["cf_month"], "Scenario", 4, 0, 2, 2),
         counter("cf_kpi_actual", "cf_actual_kpi", "sum(net_cash)", "SUM(`net_cash`)", False,
                 "Net Cash Flow (Actual)", 0, 2, fmt=FMT_MONEY),
         counter("cf_kpi_var", "cf_accuracy", "sum(variance)", "SUM(`variance`)", False,
                 "Forecast Variance (Actual − Forecast)", 2, 2, fmt=FMT_MONEY),
         counter("cf_kpi_acc", "cf_accuracy", "avg(accuracy_frac)", "AVG(`accuracy_frac`)", False,
                 "Avg Forecast Accuracy (floored)", 4, 2, fmt=FMT_PCT),
         bar("cf_avf", "cf_month", "month", "`month`",
             [("sum(net_cash)", "SUM(`net_cash`)", "Net Cash Flow")], "Net Cash Flow by Month", 0, 5, 3, 6,
             xtype="temporal", color="scenario", colorexpr="`scenario`", grouped=True, fmt=FMT_MONEY),
         bar("cf_inout", "cf_month", "month", "`month`",
             [("sum(cash_in)", "SUM(`cash_in`)", "Inflow"), ("sum(cash_out)", "SUM(`cash_out`)", "Outflow")],
             "Cash Inflow vs Outflow", 3, 5, 3, 6, xtype="temporal", grouped=True, fmt=FMT_MONEY),
         bar("cf_var_month", "cf_accuracy", "month", "`month`",
             [("sum(variance)", "SUM(`variance`)", "Forecast Variance")],
             "Forecast Variance by Month (Actual − Forecast)", 0, 11, 2, 5, xtype="temporal", fmt=FMT_MONEY),
         line("cf_acc", "cf_accuracy", "month", "`month`",
              [("accuracy_frac", "`accuracy_frac`", "Forecast Accuracy")],
              "Forecast Accuracy % (floored, months w/ actuals)", 2, 11, 2, 5, xtype="temporal", disagg=True, fmt=FMT_PCT),
         line("cf_ytd_line", "cf_ytd_actual", "month", "`month`",
              [("sum(ytd_cash)", "SUM(`ytd_cash`)", "YTD Net Cash (Actual)")],
              "YTD Net Cash Flow (Actual)", 4, 11, 2, 5, xtype="temporal", fmt=FMT_MONEY)]
    return {"name": "cash", "displayName": "Cash & Liquidity", "pageType": "PAGE_TYPE_CANVAS", "layout": L}

def wc_page():
    L = [text("wc_title", 0, 0, 4, 1, "## Working Capital — AR / AP"),
         filter_widget("wc_flt_arap", "ar_ap", ["oi_aging", "oi_party", "oi_dsodpo"], "AR / AP", 4, 0, 2, 2),
         counter("wc_dso", "kpi_dso", "dso", "`dso`", True, "DSO (days)", 0, 2, fmt=FMT_DAYS),
         counter("wc_dpo", "kpi_dpo", "dpo", "`dpo`", True, "DPO (days)", 2, 2, fmt=FMT_DAYS),
         bar("wc_dsodpo", "oi_dsodpo", "ar_ap", "`ar_ap`",
             [("avg_days", "`avg_days`", "Days (amount-weighted)")], "DSO / DPO (amount-weighted)", 4, 2, 2, 3, disagg=True, fmt=FMT_DAYS),
         bar("wc_aging", "oi_aging", "aging_bucket", "`aging_bucket`",
             [("sum(open_amount)", "SUM(`open_amount`)", "Open Amount")], "Open Amount by Aging Bucket", 0, 5, 3, 6,
             color="ar_ap", colorexpr="`ar_ap`", fmt=FMT_MONEY),
         bar("wc_overdue", "oi_aging", "ar_ap", "`ar_ap`",
             [("sum(open_amount)", "SUM(`open_amount`)", "Open"), ("sum(overdue_amount)", "SUM(`overdue_amount`)", "Overdue")],
             "Open vs Overdue", 3, 5, 3, 6, grouped=True, fmt=FMT_MONEY),
         table("wc_party", "oi_party",
               [("ar_ap", "`ar_ap`", "AR/AP"), ("party", "`party`", "Business Partner"),
                ("open_amount", "`open_amount`", "Open Amount", FMT_MONEY)], "Open by Business Partner", 0, 11, 6, 5, disagg=True)]
    return {"name": "working_capital", "displayName": "Working Capital (AR/AP)", "pageType": "PAGE_TYPE_CANVAS", "layout": L}

def global_filters():
    L = [filter_widget("g_company", "company", COMPANY_DS, "Company", 0, 0, 2, 3),
         filter_widget("g_year", "fiscal_year", YEAR_DS, "Fiscal Year", 2, 0, 2, 3),
         filter_widget("g_daterange", "month", MONTH_DS, "Date Range", 4, 0, 2, 3, wtype="filter-date-range-picker")]
    return {"name": "filters", "displayName": "Filters", "pageType": "PAGE_TYPE_GLOBAL_FILTERS", "layout": L}

def build():
    data = dict(D)
    if USE_CUSTOM:
        data.update(CUSTOM_D)
    datasets = [{"name": n, "displayName": n, "queryLines": [sql]} for n, sql in data.items()]
    pages = [overview(), gl_page(), cc_page(), cash_page(), wc_page(), global_filters()]

    if USE_CUSTOM:
        pg = {p["name"]: p for p in pages}
        pg["cost_center"]["layout"].append(
            custom_vega("cc_radial", "cc_hier",
                        [("$valueField", "`spend`"), ("$colorField", "`hier_l1`")], radial_spec(),
                        "Spend Share by Hierarchy L1 (radial)", 0, 14, 6, 6))
        pg["working_capital"]["layout"].append(
            custom_vega("wc_gauge", "gauge_clear",
                        [("$valueField", "`cleared`"), ("$totalField", "`total`")], gauge_spec(),
                        "AR/AP Items Cleared", 0, 16, 2, 5))
        pg["working_capital"]["layout"].append(
            text("wc_gauge_note", 2, 16, 4, 5,
                 "### Collection health\nShare of AR/AP items cleared vs. total. Green >66%, amber 33-66%, red <33%."))

    dash = {"datasets": datasets, "pages": pages,
            "uiSettings": {"theme": CONFIG["theme"], "applyModeEnabled": False}}
    out = ARGS.output
    with open(out, "w") as f:
        json.dump(dash, f, indent=2)
    print(f"wrote {out} ({len(datasets)} datasets, {len(pages)} pages, theme+formats applied)")

if __name__ == "__main__":
    build()
