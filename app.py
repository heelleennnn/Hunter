import os
import pandas as pd
from dash import Dash, dcc, html, Input, Output, dash_table
import plotly.express as px

DATA_PATH = "dashboard_data.csv"


def postcode_to_state(postcode):
    """Map Australian postcode ranges to states/territories."""
    if pd.isna(postcode):
        return "Unknown"
    try:
        pc = int(float(postcode))
    except (ValueError, TypeError):
        return "Unknown"

    if 1000 <= pc <= 1999 or 2000 <= pc <= 2599 or 2619 <= pc <= 2899 or 2921 <= pc <= 2999:
        return "NSW"
    if 200 <= pc <= 299 or 2600 <= pc <= 2618 or 2900 <= pc <= 2920:
        return "ACT"
    if 3000 <= pc <= 3999 or 8000 <= pc <= 8999:
        return "VIC"
    if 4000 <= pc <= 4999 or 9000 <= pc <= 9999:
        return "QLD"
    if 5000 <= pc <= 5999:
        return "SA"
    if 6000 <= pc <= 6999:
        return "WA"
    if 7000 <= pc <= 7999:
        return "TAS"
    if 800 <= pc <= 999:
        return "NT"
    return "Unknown"


def clean_text_series(series):
    """Clean a text column while keeping blank values as missing."""
    return (
        series
        .astype("string")
        .str.strip()
        .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA, "NaN": pd.NA})
    )


def load_data():
    df = pd.read_csv(DATA_PATH)

    # Parse Australian-style dates such as 11/5/26 as 11 May 2026.
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")

    # Clean postcode and derive state from postcode ranges.
    df["Postcode_clean"] = pd.to_numeric(df["Postcode"], errors="coerce")
    df["Postcode_label"] = df["Postcode_clean"].apply(
        lambda x: "Unknown" if pd.isna(x) else str(int(x))
    )
    df["Derived State"] = df["Postcode_clean"].apply(postcode_to_state)

    # Clean dimensions used in charts and tables.
    text_columns = [
        "Location",
        "Form",
        "Registration Type",
        "Badge",
        "Colour",
        "Second-preference Colour",
        "Interior",
        "Optional Package",
        "Trade-in Yes/No",
        "Year",
        "Vehicle",
        "Model.1",
        "Odometer",
    ]
    for col in text_columns:
        if col in df.columns:
            df[col] = clean_text_series(df[col])

    # Main chart dimensions still use Unknown so the original dashboard does not drop leads.
    for col in ["Location", "Form"]:
        df[col] = df[col].fillna("Unknown")

    # Standardise trade-in values for the Yes/No bar chart.
    if "Trade-in Yes/No" in df.columns:
        trade = df["Trade-in Yes/No"].astype("string").str.strip().str.lower()
        df["Trade-in Clean"] = trade.map({
            "yes": "Yes",
            "y": "Yes",
            "no": "No",
            "n": "No",
        }).fillna(df["Trade-in Yes/No"])
    else:
        df["Trade-in Clean"] = pd.NA

    return df


df = load_data()

min_date = df["Date"].min()
max_date = df["Date"].max()

app = Dash(__name__)
server = app.server


def metric_card(title, value, font_size="26px"):
    return [
        html.Div(title, className="metric-title"),
        html.Div(value, className="metric-value", style={"fontSize": font_size}),
    ]


def table_card(title, table_id):
    return html.Div(
        className="chart-card",
        children=[
            html.H3(title, style={"marginTop": "0", "marginBottom": "12px"}),
            html.Div(id=table_id),
        ],
    )


app.layout = html.Div(
    style={"fontFamily": "Arial, sans-serif", "backgroundColor": "#f7f8fa", "padding": "24px"},
    children=[
        html.Div(
            style={"maxWidth": "1200px", "margin": "0 auto"},
            children=[
                html.H1("Digital Leads Dashboard", style={"marginBottom": "4px"}),
                html.P(
                    "Overview of lead trends, postcode-derived states, form types, locations, registration details, preferences, and trade-in information.",
                    style={"color": "#666", "marginTop": "0"},
                ),

                html.Div(
                    style={
                        "display": "grid",
                        "gridTemplateColumns": "repeat(4, 1fr)",
                        "gap": "16px",
                        "margin": "24px 0",
                    },
                    children=[
                        html.Div(id="total-leads-card", className="metric-card"),
                        html.Div(id="date-range-card", className="metric-card"),
                        html.Div(id="top-form-card", className="metric-card"),
                        html.Div(id="top-location-card", className="metric-card"),
                    ],
                ),

                html.Div(
                    style={"backgroundColor": "white", "padding": "16px", "borderRadius": "14px", "boxShadow": "0 2px 10px rgba(0,0,0,0.06)", "marginBottom": "20px"},
                    children=[
                        html.H3("Filters", style={"marginTop": "0"}),
                        html.Div(
                            style={"display": "grid", "gridTemplateColumns": "1.2fr 1fr 1fr", "gap": "16px"},
                            children=[
                                html.Div([
                                    html.Label("Date range"),
                                    dcc.DatePickerRange(
                                        id="date-filter",
                                        min_date_allowed=min_date,
                                        max_date_allowed=max_date,
                                        start_date=min_date,
                                        end_date=max_date,
                                        display_format="DD/MM/YYYY",
                                        style={"width": "100%"},
                                    ),
                                ]),
                                html.Div([
                                    html.Label("State derived from postcode"),
                                    dcc.Dropdown(
                                        id="state-filter",
                                        options=[{"label": s, "value": s} for s in sorted(df["Derived State"].dropna().unique())],
                                        value=[],
                                        multi=True,
                                        placeholder="All states",
                                    ),
                                ]),
                                html.Div([
                                    html.Label("Form type"),
                                    dcc.Dropdown(
                                        id="form-filter",
                                        options=[{"label": f, "value": f} for f in sorted(df["Form"].dropna().unique())],
                                        value=[],
                                        multi=True,
                                        placeholder="All forms",
                                    ),
                                ]),
                            ],
                        ),
                    ],
                ),

                html.Div(
                    className="chart-card",
                    style={"marginBottom": "20px"},
                    children=[dcc.Graph(id="date-trend", style={"height": "520px"})],
                ),

                html.Div(
                    style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "20px", "marginBottom": "20px"},
                    children=[
                        html.Div(className="chart-card", children=[dcc.Graph(id="state-bar")]),
                        html.Div(className="chart-card", children=[dcc.Graph(id="form-bar")]),
                        html.Div(className="chart-card", children=[dcc.Graph(id="location-bar")]),
                        html.Div(className="chart-card", children=[dcc.Graph(id="trade-in-bar")]),
                    ],
                ),

                html.H2("Lead Details Summary", style={"marginTop": "28px"}),
                html.P(
                    "Blank values are ignored in the summary tables below.",
                    style={"color": "#666", "marginTop": "0"},
                ),

                html.Div(
                    style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "20px", "marginBottom": "20px"},
                    children=[
                        table_card("Registration Type", "registration-table"),
                        table_card("Badge", "badge-table"),
                        table_card("Colour", "colour-table"),
                        table_card("Second Preference Colour", "second-preference-table"),
                        table_card("Interior", "interior-table"),
                        table_card("Optional Package", "optional-package-table"),
                    ],
                ),

                html.Div(
                    className="chart-card",
                    children=[
                        html.H3("Trade-in Vehicle Information", style={"marginTop": "0", "marginBottom": "12px"}),
                        html.P(
                            "Rows are shown only when at least one trade-in vehicle field has an entry.",
                            style={"color": "#666", "marginTop": "0"},
                        ),
                        html.Div(id="trade-in-summary-table"),
                    ],
                ),
            ],
        ),
    ],
)

app.index_string = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>Digital Leads Dashboard</title>
        {%favicon%}
        {%css%}
        <style>
            .metric-card, .chart-card {
                background: white;
                border-radius: 14px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.06);
                padding: 16px;
            }
            .metric-title { color: #666; font-size: 13px; margin-bottom: 6px; }
            .metric-value { font-size: 26px; font-weight: 700; }
            label { font-weight: 600; display: block; margin-bottom: 6px; }
            h1, h2, h3 { color: #2b3f63; }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""


def filter_data(start_date, end_date, states, forms):
    filtered = df.copy()
    if start_date:
        filtered = filtered[filtered["Date"] >= pd.to_datetime(start_date)]
    if end_date:
        filtered = filtered[filtered["Date"] <= pd.to_datetime(end_date)]
    if states:
        filtered = filtered[filtered["Derived State"].isin(states)]
    if forms:
        filtered = filtered[filtered["Form"].isin(forms)]
    return filtered


def value_count_table(dff, column, label):
    if column not in dff.columns:
        data = []
    else:
        counts = (
            dff[column]
            .dropna()
            .astype("string")
            .str.strip()
        )
        counts = counts[counts != ""]
        data = counts.value_counts().reset_index()
        data.columns = [label, "Count"]
        data["Share"] = (data["Count"] / data["Count"].sum() * 100).round(1).astype(str) + "%" if not data.empty else []
        data = data.to_dict("records")

    return dash_table.DataTable(
        columns=[{"name": label, "id": label}, {"name": "Count", "id": "Count"}, {"name": "Share", "id": "Share"}],
        data=data,
        page_size=8,
        sort_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"textAlign": "left", "padding": "8px", "fontFamily": "Arial", "fontSize": "13px"},
        style_header={"fontWeight": "700", "backgroundColor": "#f1f4f8"},
        style_data_conditional=[{"if": {"row_index": "odd"}, "backgroundColor": "#fafafa"}],
    )


def trade_in_vehicle_table(dff):
    source_cols = ["Year", "Vehicle", "Model.1", "Odometer"]
    display_names = {
        "Year": "Year",
        "Vehicle": "Vehicle",
        "Model.1": "Model",
        "Odometer": "Odometer",
    }
    existing_cols = [col for col in source_cols if col in dff.columns]
    trade_df = dff[existing_cols].copy()

    if trade_df.empty:
        output = pd.DataFrame(columns=list(display_names.values()))
    else:
        has_entry = trade_df.notna().any(axis=1)
        output = trade_df.loc[has_entry].rename(columns=display_names)
        if "Odometer" in output.columns:
            output["Odometer"] = output["Odometer"].apply(
                lambda x: "" if pd.isna(x) else f"{float(x):,.0f}" if str(x).replace(".", "", 1).isdigit() else str(x)
            )
        output = output.fillna("")

    return dash_table.DataTable(
        columns=[{"name": c, "id": c} for c in output.columns],
        data=output.to_dict("records"),
        page_size=12,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"textAlign": "left", "padding": "8px", "fontFamily": "Arial", "fontSize": "13px"},
        style_header={"fontWeight": "700", "backgroundColor": "#f1f4f8"},
        style_data_conditional=[{"if": {"row_index": "odd"}, "backgroundColor": "#fafafa"}],
    )


@app.callback(
    Output("total-leads-card", "children"),
    Output("date-range-card", "children"),
    Output("top-form-card", "children"),
    Output("top-location-card", "children"),
    Output("date-trend", "figure"),
    Output("state-bar", "figure"),
    Output("form-bar", "figure"),
    Output("location-bar", "figure"),
    Output("trade-in-bar", "figure"),
    Output("registration-table", "children"),
    Output("badge-table", "children"),
    Output("colour-table", "children"),
    Output("second-preference-table", "children"),
    Output("interior-table", "children"),
    Output("optional-package-table", "children"),
    Output("trade-in-summary-table", "children"),
    Input("date-filter", "start_date"),
    Input("date-filter", "end_date"),
    Input("state-filter", "value"),
    Input("form-filter", "value"),
)
def update_dashboard(start_date, end_date, states, forms):
    dff = filter_data(start_date, end_date, states, forms)

    total_leads = len(dff)
    date_min = dff["Date"].min()
    date_max = dff["Date"].max()
    date_text = "No data" if pd.isna(date_min) else f"{date_min:%d %b %Y} – {date_max:%d %b %Y}"
    top_form = "No data" if dff.empty else dff["Form"].value_counts().idxmax()
    top_location = "No data" if dff.empty else dff["Location"].value_counts().idxmax()

    total_card = metric_card("Total leads", f"{total_leads:,}")
    date_card = metric_card("Date range", date_text, "18px")
    form_card = metric_card("Top form", top_form, "18px")
    location_card = metric_card("Top location", top_location, "18px")

    trend = dff.dropna(subset=["Date"]).groupby("Date").size().reset_index(name="Leads")
    fig_trend = px.line(trend, x="Date", y="Leads", markers=True, title="Lead Trend by Date")
    fig_trend.update_layout(margin=dict(l=20, r=20, t=55, b=20))

    state_counts = dff["Derived State"].value_counts().reset_index()
    state_counts.columns = ["Derived State", "Leads"]
    fig_state = px.bar(state_counts, x="Derived State", y="Leads", title="Leads by Postcode-Derived State")
    fig_state.update_layout(margin=dict(l=20, r=20, t=55, b=20))

    form_counts = dff["Form"].value_counts().reset_index()
    form_counts.columns = ["Form", "Leads"]
    fig_form = px.bar(form_counts, x="Leads", y="Form", orientation="h", title="Leads by Form Type")
    fig_form.update_layout(yaxis={"categoryorder": "total ascending"}, margin=dict(l=20, r=20, t=55, b=20))

    location_counts = dff["Location"].value_counts().head(15).reset_index()
    location_counts.columns = ["Location", "Leads"]
    fig_location = px.bar(location_counts, x="Leads", y="Location", orientation="h", title="Top 15 Locations by Leads")
    fig_location.update_layout(yaxis={"categoryorder": "total ascending"}, margin=dict(l=20, r=20, t=55, b=20))

    trade_counts = dff["Trade-in Clean"].dropna().astype("string").str.strip()
    trade_counts = trade_counts[trade_counts != ""].value_counts().reset_index()
    trade_counts.columns = ["Trade-in", "Leads"]
    fig_trade = px.bar(trade_counts, x="Trade-in", y="Leads", title="Trade-in Yes/No")
    fig_trade.update_layout(margin=dict(l=20, r=20, t=55, b=20))

    registration_table = value_count_table(dff, "Registration Type", "Registration Type")
    badge_table = value_count_table(dff, "Badge", "Badge")
    colour_table = value_count_table(dff, "Colour", "Colour")
    second_preference_table = value_count_table(dff, "Second-preference Colour", "Second Preference")
    interior_table = value_count_table(dff, "Interior", "Interior")
    optional_package_table = value_count_table(dff, "Optional Package", "Optional Package")
    trade_summary_table = trade_in_vehicle_table(dff)

    return (
        total_card,
        date_card,
        form_card,
        location_card,
        fig_trend,
        fig_state,
        fig_form,
        fig_location,
        fig_trade,
        registration_table,
        badge_table,
        colour_table,
        second_preference_table,
        interior_table,
        optional_package_table,
        trade_summary_table,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False)
