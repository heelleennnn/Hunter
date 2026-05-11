import os
import pandas as pd
from dash import Dash, dcc, html, Input, Output
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

    # Clean dimensions for charts.
    for col in ["Location", "Form"]:
        df[col] = df[col].fillna("Unknown").astype(str).str.strip()
        df.loc[df[col] == "", col] = "Unknown"

    return df


df = load_data()

min_date = df["Date"].min()
max_date = df["Date"].max()

app = Dash(__name__)
server = app.server

app.layout = html.Div(
    style={"fontFamily": "Arial, sans-serif", "backgroundColor": "#f7f8fa", "padding": "24px"},
    children=[
        html.Div(
            style={"maxWidth": "1200px", "margin": "0 auto"},
            children=[
                html.H1("Digital Leads Dashboard", style={"marginBottom": "4px"}),
                html.P(
                    "Basic overview of lead trends, postcode-derived states, form types, and locations.",
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
                    style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "20px"},
                    children=[
                        html.Div(className="chart-card", children=[dcc.Graph(id="date-trend")]),
                        html.Div(className="chart-card", children=[dcc.Graph(id="state-bar")]),
                        html.Div(className="chart-card", children=[dcc.Graph(id="form-bar")]),
                        html.Div(className="chart-card", children=[dcc.Graph(id="location-bar")]),
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


@app.callback(
    Output("total-leads-card", "children"),
    Output("date-range-card", "children"),
    Output("top-form-card", "children"),
    Output("top-location-card", "children"),
    Output("date-trend", "figure"),
    Output("state-bar", "figure"),
    Output("form-bar", "figure"),
    Output("location-bar", "figure"),
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

    total_card = [html.Div("Total leads", className="metric-title"), html.Div(f"{total_leads:,}", className="metric-value")]
    date_card = [html.Div("Date range", className="metric-title"), html.Div(date_text, className="metric-value", style={"fontSize": "18px"})]
    form_card = [html.Div("Top form", className="metric-title"), html.Div(top_form, className="metric-value", style={"fontSize": "18px"})]
    location_card = [html.Div("Top location", className="metric-title"), html.Div(top_location, className="metric-value", style={"fontSize": "18px"})]

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

    return total_card, date_card, form_card, location_card, fig_trend, fig_state, fig_form, fig_location


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False)
