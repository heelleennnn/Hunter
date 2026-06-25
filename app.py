import os
import pandas as pd
from dash import Dash, dcc, html, Input, Output, dash_table
import plotly.express as px

DATA_PATH = "dashboard_data.csv"
DEALERLIST_PATH = "dealerlist.csv"
WEEKLY_SUMMARY_PATH = "weekly_new_data_summary.csv"
JAC_MOTORS_COMBINED_SUMMARY_PATH = "jac_motors_combined_summary.csv"
JAC_MOTORS_COMBINED_DETAIL_PATH = "jac_motors_combined_detail.csv"

KPI_TARGETS = {
    "Metro": 20,
    "Rural": 10,
}

DASHBOARD_COLUMNS = [
    "Lead ID",
    "Date",
    "Location",
    "Form",
    "Postcode",
    "Make",
    "Model",
    "State",
    "Registration Type",
    "Badge",
    "Colour",
    "Second-preference Colour",
    "Optional Package",
    "Trade-in Yes/No",
    "Year",
    "Vehicle",
    "Model.1",
    "Odometer",
]


def load_dealerlist():
    """Load dealer type and combine rules from dealerlist.csv."""
    if not os.path.exists(DEALERLIST_PATH):
        return pd.DataFrame(columns=["Dealer", "Dealer Type", "Is Combined", "Combine To"])

    dealerlist = pd.read_csv(DEALERLIST_PATH)
    if "Is Combined" not in dealerlist.columns and "是否combine" in dealerlist.columns:
        dealerlist = dealerlist.rename(columns={"是否combine": "Is Combined"})

    for col in ["Dealer", "Dealer Type", "Is Combined", "Combine To"]:
        if col not in dealerlist.columns:
            dealerlist[col] = ""

    dealerlist["Dealer"] = clean_text_series(dealerlist["Dealer"])
    dealerlist["Dealer Type"] = clean_text_series(dealerlist["Dealer Type"])
    dealerlist["Combine To"] = clean_text_series(dealerlist["Combine To"])
    dealerlist["Is Combined"] = (
        dealerlist["Is Combined"]
        .astype("string")
        .str.strip()
        .str.casefold()
        .isin(["true", "yes", "y", "1"])
    )
    return dealerlist.dropna(subset=["Dealer"]).copy()


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


DEALERLIST = load_dealerlist()


def dealer_lookup(dealerlist, value_column):
    if dealerlist.empty or value_column not in dealerlist.columns:
        return {}
    return (
        dealerlist
        .dropna(subset=["Dealer", value_column])
        .assign(_dealer_key=lambda d: d["Dealer"].astype("string").str.strip().str.casefold())
        .set_index("_dealer_key")[value_column]
        .to_dict()
    )


def apply_location_reassignments(df, dealerlist):
    """Apply dealer merge/reallocation rules and keep the original value visible."""
    if "Location" not in df.columns:
        return df

    if dealerlist.empty:
        df["Original Location"] = df["Location"]
        df["Combine To"] = ""
        df["Is Combined"] = False
        df["Reallocation Note"] = ""
        return df

    combine_rules = dealerlist[
        dealerlist["Is Combined"] & dealerlist["Combine To"].notna()
    ].copy()
    normalised_reassignments = dealer_lookup(combine_rules, "Combine To")

    original_location = df["Location"].copy()
    original_key = df["Location"].astype("string").str.strip().str.casefold()
    reassigned_location = (
        original_key.map(normalised_reassignments)
    )

    df["Original Location"] = original_location
    df["Location"] = reassigned_location.fillna(df["Location"])
    df["Combine To"] = reassigned_location.fillna("")
    df["Is Combined"] = reassigned_location.notna()
    df["Reallocation Note"] = ""
    changed = original_location.notna() & df["Location"].ne(original_location)
    df.loc[changed, "Reallocation Note"] = (
        original_location[changed].astype("string") + " -> " + df.loc[changed, "Location"].astype("string")
    )
    return df


def add_dealer_kpi_columns(df, dealerlist):
    """Classify dealers from dealerlist.csv and attach KPI targets."""
    if "Location" not in df.columns:
        return df

    dealer_type_lookup = dealer_lookup(dealerlist, "Dealer Type")
    df["Dealer Type"] = (
        df["Location"]
        .astype("string")
        .str.strip()
        .str.casefold()
        .map(dealer_type_lookup)
        .fillna("Rural")
    )
    df.loc[df["Location"].eq("Unknown"), "Dealer Type"] = "Unknown"
    df["KPI Target"] = df["Dealer Type"].map(KPI_TARGETS)
    return df


def normalise_dashboard_columns(df):
    """Keep the app aligned with the de-identified dashboard_data.csv shape."""
    df = df.copy()

    # dashboard_data.csv intentionally has two "Model" headers. Pandas renames
    # the second one to "Model.1", which the trade-in table uses.
    if "Model.1" not in df.columns:
        df["Model.1"] = ""

    for col in DASHBOARD_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    return df


def load_data():
    df = pd.read_csv(DATA_PATH, dtype=str, keep_default_na=False)
    df = normalise_dashboard_columns(df)

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
        "State",
        "Registration Type",
        "Badge",
        "Colour",
        "Second-preference Colour",
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

    # If postcode is missing or invalid, use the existing State column as a fallback.
    if "State" in df.columns:
        state_fallback = df["State"].astype("string").str.strip().str.upper()
        df["Derived State"] = df["Derived State"].mask(
            df["Derived State"].eq("Unknown") & state_fallback.notna() & state_fallback.ne(""),
            state_fallback,
        )

    # Main chart dimensions still use Unknown so the original dashboard does not drop leads.
    for col in ["Location", "Form"]:
        df[col] = df[col].fillna("Unknown")

    df = apply_location_reassignments(df, DEALERLIST)
    df = add_dealer_kpi_columns(df, DEALERLIST)

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


def latest_week_window(source_df):
    valid_dates = source_df["Date"].dropna() if "Date" in source_df.columns else pd.Series(dtype="datetime64[ns]")
    if valid_dates.empty:
        return None, None
    end_date = valid_dates.max()
    start_date = end_date - pd.Timedelta(days=6)
    return start_date, end_date


def latest_week_data(source_df):
    start_date, end_date = latest_week_window(source_df)
    if start_date is None:
        return source_df.iloc[0:0].copy(), start_date, end_date
    weekly_df = source_df[source_df["Date"].between(start_date, end_date, inclusive="both")].copy()
    return weekly_df, start_date, end_date


def build_dealer_summary(source_df):
    output_columns = [
        "Original Location",
        "Dealer Type",
        "Is Combined",
        "Combine To",
        "Final Location",
        "Original Enquiries",
        "Final Location Enquiries",
    ]
    if source_df.empty or "Original Location" not in source_df.columns:
        return pd.DataFrame(columns=output_columns)

    original_counts = (
        source_df
        .groupby(["Original Location", "Location"], dropna=False)
        .size()
        .reset_index(name="Original Enquiries")
        .rename(columns={"Location": "Final Location"})
    )
    final_counts = (
        source_df
        .groupby("Location", dropna=False)
        .size()
        .rename("Final Location Enquiries")
    )
    dealer_type_map = dealer_lookup(DEALERLIST, "Dealer Type")
    combine_map = dealer_lookup(DEALERLIST[DEALERLIST["Is Combined"]], "Combine To") if not DEALERLIST.empty else {}

    original_counts["Dealer Type"] = (
        original_counts["Original Location"]
        .astype("string")
        .str.strip()
        .str.casefold()
        .map(dealer_type_map)
        .fillna("Rural")
    )
    original_counts["Combine To"] = (
        original_counts["Original Location"]
        .astype("string")
        .str.strip()
        .str.casefold()
        .map(combine_map)
        .fillna("")
    )
    original_counts["Is Combined"] = original_counts["Combine To"].ne("")
    original_counts["Final Location Enquiries"] = original_counts["Final Location"].map(final_counts).fillna(0).astype(int)

    return (
        original_counts[output_columns]
        .sort_values(["Is Combined", "Original Enquiries", "Original Location"], ascending=[False, False, True])
        .reset_index(drop=True)
    )


def build_combined_destination_summary(source_df, destination="JAC Motors"):
    output_columns = [
        "Original Location",
        "Dealer Type",
        "Combine To",
        "Leads Moved",
        "Destination Total Leads",
    ]
    required_cols = ["Original Location", "Location", "Combine To", "Is Combined"]
    if source_df.empty or not all(col in source_df.columns for col in required_cols):
        return pd.DataFrame(columns=output_columns)

    destination_key = destination.strip().casefold()
    moved_df = source_df[
        source_df["Is Combined"]
        & source_df["Combine To"].astype("string").str.strip().str.casefold().eq(destination_key)
    ].copy()

    if moved_df.empty:
        return pd.DataFrame(columns=output_columns)

    destination_total = (
        source_df["Location"]
        .astype("string")
        .str.strip()
        .str.casefold()
        .eq(destination_key)
        .sum()
    )
    dealer_type_map = dealer_lookup(DEALERLIST, "Dealer Type")

    output = (
        moved_df
        .groupby(["Original Location", "Combine To"], dropna=False)
        .size()
        .reset_index(name="Leads Moved")
        .sort_values(["Leads Moved", "Original Location"], ascending=[False, True])
    )
    output["Dealer Type"] = (
        output["Original Location"]
        .astype("string")
        .str.strip()
        .str.casefold()
        .map(dealer_type_map)
        .fillna("Rural")
    )
    output["Destination Total Leads"] = int(destination_total)
    return output[output_columns].reset_index(drop=True)


def build_combined_destination_detail(source_df, destination="JAC Motors"):
    detail_columns = [
        "Lead ID",
        "Date",
        "Original Location",
        "Location",
        "Form",
        "Postcode",
        "Derived State",
        "Make",
        "Model",
        "State",
        "Registration Type",
        "Badge",
        "Colour",
        "Second-preference Colour",
        "Optional Package",
        "Trade-in Yes/No",
        "Year",
        "Vehicle",
        "Model.1",
        "Odometer",
    ]
    required_cols = ["Original Location", "Combine To", "Is Combined"]
    if source_df.empty or not all(col in source_df.columns for col in required_cols):
        return pd.DataFrame(columns=detail_columns)

    destination_key = destination.strip().casefold()
    output = source_df[
        source_df["Is Combined"]
        & source_df["Combine To"].astype("string").str.strip().str.casefold().eq(destination_key)
    ].copy()

    for col in detail_columns:
        if col not in output.columns:
            output[col] = ""

    output = output[detail_columns].sort_values(["Original Location", "Date", "Lead ID"], ascending=[True, False, False])
    return output.reset_index(drop=True)


def format_table_dates(output, columns=None):
    if output.empty:
        return output
    output = output.copy()
    date_columns = columns or ["Date"]
    for col in date_columns:
        if col in output.columns:
            output[col] = output[col].apply(lambda x: "" if pd.isna(x) else f"{x:%d/%m/%Y}" if hasattr(x, "strftime") else x)
    return output


def write_weekly_summary():
    weekly_df, start_date, end_date = latest_week_data(df)
    summary = build_dealer_summary(weekly_df)
    if start_date is not None:
        summary.insert(0, "Week Start", f"{start_date:%d/%m/%Y}")
        summary.insert(1, "Week End", f"{end_date:%d/%m/%Y}")
    summary.to_csv(WEEKLY_SUMMARY_PATH, index=False, encoding="utf-8-sig")
    return summary


WEEKLY_DEALER_SUMMARY = write_weekly_summary()


def write_jac_motors_combined_exports():
    summary = build_combined_destination_summary(df, "JAC Motors")
    detail = build_combined_destination_detail(df, "JAC Motors")
    format_table_dates(summary).to_csv(JAC_MOTORS_COMBINED_SUMMARY_PATH, index=False, encoding="utf-8-sig")
    format_table_dates(detail).to_csv(JAC_MOTORS_COMBINED_DETAIL_PATH, index=False, encoding="utf-8-sig")
    return summary, detail


JAC_MOTORS_COMBINED_SUMMARY, JAC_MOTORS_COMBINED_DETAIL = write_jac_motors_combined_exports()


def get_exact_jac_motors_states(source_df):
    """Return states for rows where Location is exactly JAC Motors."""
    if "Location" not in source_df.columns or "Derived State" not in source_df.columns:
        return []
    jac_df = source_df[
        source_df["Location"]
        .astype("string")
        .str.strip()
        .str.casefold()
        .eq("jac motors")
    ].copy()
    return sorted(jac_df["Derived State"].dropna().astype("string").unique())


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
                        "gridTemplateColumns": "repeat(2, 1fr)",
                        "gap": "16px",
                        "margin": "24px 0",
                    },
                    children=[
                        html.Div(id="total-leads-card", className="metric-card"),
                        html.Div(id="date-range-card", className="metric-card"),
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
                    className="chart-card",
                    style={"marginBottom": "20px"},
                    children=[
                        html.H3("Dealer KPI Tracking", style={"marginTop": "0", "marginBottom": "12px"}),
                        html.P(
                            "Metro dealers target 20 leads. Rural dealers target 10 leads. 'JAC Motors' contains leads awaiting Jason's reallocation confirmation.",
                            style={"color": "#666", "marginTop": "0"},
                        ),
                        html.Div(id="dealer-kpi-table"),
                    ],
                ),

                html.Div(
                    className="chart-card",
                    style={"marginBottom": "20px"},
                    children=[
                        html.H3("Latest Week Dealer Enquiry Summary", style={"marginTop": "0", "marginBottom": "12px"}),
                        html.P(
                            f"This uses the latest 7-day window in the loaded data and reads dealer type/combine rules from {DEALERLIST_PATH}. A CSV is also generated as {WEEKLY_SUMMARY_PATH}.",
                            style={"color": "#666", "marginTop": "0"},
                        ),
                        html.Div(id="weekly-summary-label", style={"fontWeight": "700", "marginBottom": "10px"}),
                        html.Div(id="weekly-dealer-summary-table"),
                    ],
                ),

                html.Div(
                    className="chart-card",
                    style={"marginBottom": "20px"},
                    children=[
                        html.H3("JAC Motors Combined Dealer Enquiries", style={"marginTop": "0", "marginBottom": "12px"}),
                        html.P(
                            f"Shows dealers marked Is Combined = true and Combine To = JAC Motors in {DEALERLIST_PATH}. Full unfiltered exports are generated as {JAC_MOTORS_COMBINED_SUMMARY_PATH} and {JAC_MOTORS_COMBINED_DETAIL_PATH}.",
                            style={"color": "#666", "marginTop": "0"},
                        ),
                        html.Div(
                            style={"maxWidth": "420px", "marginBottom": "14px"},
                            children=[
                                html.Label("Combine date range"),
                                dcc.DatePickerRange(
                                    id="combine-date-filter",
                                    min_date_allowed=min_date,
                                    max_date_allowed=max_date,
                                    start_date=min_date,
                                    end_date=max_date,
                                    display_format="DD/MM/YYYY",
                                    style={"width": "100%"},
                                ),
                            ],
                        ),
                        html.Div(id="combined-summary-label", style={"fontWeight": "700", "marginBottom": "10px"}),
                        html.H4("Summary by Original Dealer", style={"marginBottom": "10px"}),
                        html.Div(id="combined-dealer-summary-table"),
                        html.H4("Original Lead Detail", style={"marginBottom": "10px", "marginTop": "18px"}),
                        html.Div(id="combined-dealer-detail-table"),
                    ],
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

                html.H2("Hunter Order Details", style={"marginTop": "28px"}),
                html.P(
                    "Blank values are ignored in the summary tables below. Use the Badge filter to review Hunter Pro 4x4 or Hunter X 4x4 order details separately.",
                    style={"color": "#666", "marginTop": "0"},
                ),

                html.Div(
                    style={"backgroundColor": "white", "padding": "16px", "borderRadius": "14px", "boxShadow": "0 2px 10px rgba(0,0,0,0.06)", "marginBottom": "20px"},
                    children=[
                        html.Label("Badge"),
                        dcc.Dropdown(
                            id="order-badge-filter",
                            options=[
                                {"label": badge, "value": badge}
                                for badge in sorted(df["Badge"].dropna().unique())
                            ] if "Badge" in df.columns else [],
                            value=[],
                            multi=True,
                            placeholder="All badges",
                        ),
                    ],
                ),

                html.Div(
                    style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "20px", "marginBottom": "20px"},
                    children=[
                        table_card("Registration Type", "registration-table"),
                        table_card("Badge", "badge-table"),
                        table_card("Colour", "colour-table"),
                        table_card("Second Preference Colour", "second-preference-table"),
                        table_card("Optional Package", "optional-package-table"),
                    ],
                ),

                html.Div(
                    className="chart-card",
                    style={"marginBottom": "20px"},
                    children=[
                        html.H3("Trade-in Vehicle Information", style={"marginTop": "0", "marginBottom": "12px"}),
                        html.P(
                            "Rows are shown only when at least one trade-in vehicle field has an entry. This table also follows the Badge filter above.",
                            style={"color": "#666", "marginTop": "0"},
                        ),
                        html.Div(id="trade-in-summary-table"),
                    ],
                ),

                html.Div(
                    className="chart-card",
                    children=[
                        html.H3("State Summary for Location = JAC Motors", style={"marginTop": "0", "marginBottom": "12px"}),
                        html.P(
                            "This section only includes rows where the Location column is exactly 'JAC Motors'. It extracts the corresponding postcodes, derives the state, and summarises leads by state.",
                            style={"color": "#666", "marginTop": "0"},
                        ),
                        html.Div(
                            style={"maxWidth": "360px", "marginBottom": "16px"},
                            children=[
                                html.Label("State"),
                                dcc.Dropdown(
                                    id="jac-state-filter",
                                    options=[
                                        {"label": state, "value": state}
                                        for state in get_exact_jac_motors_states(df)
                                    ],
                                    value=[],
                                    multi=True,
                                    placeholder="All states",
                                ),
                            ],
                        ),
                        html.Div(id="jac-motors-state-table"),
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


def dealer_kpi_table(dff):
    output_columns = ["Location", "Dealer Type", "Leads", "KPI Target", "Gap to KPI", "Status"]
    if not all(col in dff.columns for col in ["Location", "Dealer Type", "KPI Target"]):
        output = pd.DataFrame(columns=output_columns)
    else:
        output = (
            dff
            .groupby(["Location", "Dealer Type", "KPI Target"], dropna=False)
            .size()
            .reset_index(name="Leads")
            .sort_values(["Dealer Type", "Leads", "Location"], ascending=[True, False, True])
        )
        output["KPI Target"] = output["KPI Target"].astype("Int64")
        output["Gap to KPI"] = (output["KPI Target"] - output["Leads"]).clip(lower=0).astype("Int64")
        output["Status"] = "On track"
        output.loc[output["KPI Target"].isna(), ["Gap to KPI", "Status"]] = [pd.NA, "Jason to confirm"]
        output.loc[output["Gap to KPI"].fillna(0).gt(0), "Status"] = "Below target"
        output = output[output_columns].astype("object").where(pd.notna(output), "")

    return dash_table.DataTable(
        columns=[{"name": c, "id": c} for c in output_columns],
        data=output.to_dict("records"),
        page_size=12,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"textAlign": "left", "padding": "8px", "fontFamily": "Arial", "fontSize": "13px"},
        style_header={"fontWeight": "700", "backgroundColor": "#f1f4f8"},
        style_data_conditional=[
            {"if": {"filter_query": "{Status} = 'Below target'"}, "backgroundColor": "#fff4e5"},
            {"if": {"filter_query": "{Status} = 'Jason to confirm'"}, "backgroundColor": "#fff9c4"},
            {"if": {"filter_query": "{Dealer Type} = 'Metro'"}, "fontWeight": "600"},
            {"if": {"row_index": "odd"}, "backgroundColor": "#fafafa"},
        ],
    )


def dealer_summary_table(summary_df):
    output = summary_df.copy()
    if output.empty:
        output = pd.DataFrame(columns=[
            "Original Location",
            "Dealer Type",
            "Is Combined",
            "Combine To",
            "Final Location",
            "Original Enquiries",
            "Final Location Enquiries",
        ])
    if "Is Combined" in output.columns:
        output["Is Combined"] = output["Is Combined"].map({True: "true", False: "false"}).fillna(output["Is Combined"])
    output = output.astype("object").where(pd.notna(output), "")

    return dash_table.DataTable(
        columns=[{"name": c, "id": c} for c in output.columns],
        data=output.to_dict("records"),
        page_size=12,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"textAlign": "left", "padding": "8px", "fontFamily": "Arial", "fontSize": "13px"},
        style_header={"fontWeight": "700", "backgroundColor": "#f1f4f8"},
        style_data_conditional=[
            {"if": {"filter_query": "{Is Combined} = 'true'"}, "backgroundColor": "#fff9c4"},
            {"if": {"row_index": "odd"}, "backgroundColor": "#fafafa"},
        ],
    )


def combined_dealer_summary_table(summary_df):
    output_columns = ["Original Location", "Dealer Type", "Combine To", "Leads Moved", "Destination Total Leads"]
    if summary_df.empty:
        output = pd.DataFrame(columns=output_columns)
    else:
        output = summary_df.copy()
        for col in output_columns:
            if col not in output.columns:
                output[col] = ""
        output = output[output_columns].sort_values(["Combine To", "Leads Moved"], ascending=[True, False])
    output = output.astype("object").where(pd.notna(output), "")

    return dash_table.DataTable(
        columns=[{"name": c, "id": c} for c in output_columns],
        data=output.to_dict("records"),
        page_size=8,
        sort_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"textAlign": "left", "padding": "8px", "fontFamily": "Arial", "fontSize": "13px"},
        style_header={"fontWeight": "700", "backgroundColor": "#f1f4f8"},
        style_data_conditional=[{"if": {"row_index": "odd"}, "backgroundColor": "#fafafa"}],
    )


def combined_dealer_detail_table(detail_df):
    output = format_table_dates(detail_df)
    output = output.astype("object").where(pd.notna(output), "")

    return dash_table.DataTable(
        columns=[{"name": c, "id": c} for c in output.columns],
        data=output.to_dict("records"),
        page_size=15,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"textAlign": "left", "padding": "8px", "fontFamily": "Arial", "fontSize": "13px", "minWidth": "120px", "maxWidth": "260px", "whiteSpace": "normal"},
        style_header={"fontWeight": "700", "backgroundColor": "#f1f4f8"},
        style_data_conditional=[{"if": {"row_index": "odd"}, "backgroundColor": "#fafafa"}],
    )


def optional_package_count_table(dff):
    required_cols = ["Badge", "Optional Package"]
    if not all(col in dff.columns for col in required_cols):
        output = pd.DataFrame(columns=["Badge", "Optional Package", "Count", "Share"])
    else:
        package_df = dff[required_cols].dropna(subset=["Optional Package"]).copy()
        package_df["Optional Package"] = package_df["Optional Package"].astype("string").str.strip()
        package_df["Badge"] = package_df["Badge"].fillna("Unknown").astype("string").str.strip()
        package_df = package_df[package_df["Optional Package"] != ""]

        if package_df.empty:
            output = pd.DataFrame(columns=["Badge", "Optional Package", "Count", "Share"])
        else:
            output = (
                package_df
                .groupby(["Badge", "Optional Package"], dropna=False)
                .size()
                .reset_index(name="Count")
                .sort_values(["Badge", "Count", "Optional Package"], ascending=[True, False, True])
            )
            output["Share"] = (output["Count"] / output["Count"].sum() * 100).round(1).astype(str) + "%"

    return dash_table.DataTable(
        columns=[
            {"name": "Badge", "id": "Badge"},
            {"name": "Optional Package", "id": "Optional Package"},
            {"name": "Count", "id": "Count"},
            {"name": "Share", "id": "Share"},
        ],
        data=output.to_dict("records"),
        page_size=8,
        sort_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"textAlign": "left", "padding": "8px", "fontFamily": "Arial", "fontSize": "13px"},
        style_header={"fontWeight": "700", "backgroundColor": "#f1f4f8"},
        style_data_conditional=[{"if": {"row_index": "odd"}, "backgroundColor": "#fafafa"}],
    )


def trade_in_vehicle_table(dff):
    source_cols = ["Badge", "Year", "Vehicle", "Model.1", "Odometer"]
    trade_detail_cols = ["Year", "Vehicle", "Model.1", "Odometer"]
    display_names = {
        "Badge": "Badge",
        "Year": "Year",
        "Vehicle": "Vehicle",
        "Model.1": "Model",
        "Odometer": "Odometer",
    }
    existing_cols = [col for col in source_cols if col in dff.columns]
    existing_trade_detail_cols = [col for col in trade_detail_cols if col in dff.columns]
    trade_df = dff[existing_cols].copy()

    if trade_df.empty or not existing_trade_detail_cols:
        output = pd.DataFrame(columns=[display_names[col] for col in existing_cols])
    else:
        has_entry = trade_df[existing_trade_detail_cols].notna().any(axis=1)
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


def jac_motors_state_table(dff, selected_jac_states=None):
    """Summarise exact Location = JAC Motors rows by postcode-derived state."""
    output_columns = ["Derived State", "Lead Count", "Overall Share"]

    if "Location" not in dff.columns or "Derived State" not in dff.columns:
        output = pd.DataFrame(columns=output_columns)
    else:
        # Only take the generic location category named exactly "JAC Motors".
        # This intentionally excludes dealer names such as "Northern JAC Motors"
        # or "JAC Motors Werribee".
        jac_df = dff[
            dff["Location"]
            .astype("string")
            .str.strip()
            .str.casefold()
            .eq("jac motors")
        ].copy()

        if jac_df.empty:
            output = pd.DataFrame(columns=output_columns)
        else:
            jac_df["Derived State"] = jac_df["Derived State"].fillna("Unknown").astype("string")
            total_jac_leads = len(jac_df)

            if selected_jac_states:
                jac_df = jac_df[jac_df["Derived State"].isin(selected_jac_states)]

            if jac_df.empty:
                output = pd.DataFrame(columns=output_columns)
            else:
                output = (
                    jac_df
                    .groupby("Derived State", dropna=False)
                    .size()
                    .reset_index(name="Lead Count")
                    .sort_values(["Lead Count", "Derived State"], ascending=[False, True])
                )
                # Overall Share is calculated against all exact 'JAC Motors' leads
                # before applying the dropdown filter, so each state's percentage
                # remains an overall contribution.
                output["Overall Share"] = (
                    output["Lead Count"] / total_jac_leads * 100
                ).round(1).astype(str) + "%"
                output = output[output_columns]

    return dash_table.DataTable(
        columns=[{"name": c, "id": c} for c in output.columns],
        data=output.to_dict("records"),
        page_size=8,
        sort_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"textAlign": "left", "padding": "8px", "fontFamily": "Arial", "fontSize": "13px"},
        style_header={"fontWeight": "700", "backgroundColor": "#f1f4f8"},
        style_data_conditional=[{"if": {"row_index": "odd"}, "backgroundColor": "#fafafa"}],
    )

@app.callback(
    Output("total-leads-card", "children"),
    Output("date-range-card", "children"),
    Output("date-trend", "figure"),
    Output("state-bar", "figure"),
    Output("form-bar", "figure"),
    Output("location-bar", "figure"),
    Output("trade-in-bar", "figure"),
    Output("dealer-kpi-table", "children"),
    Output("weekly-summary-label", "children"),
    Output("weekly-dealer-summary-table", "children"),
    Output("combined-summary-label", "children"),
    Output("combined-dealer-summary-table", "children"),
    Output("combined-dealer-detail-table", "children"),
    Output("registration-table", "children"),
    Output("badge-table", "children"),
    Output("colour-table", "children"),
    Output("second-preference-table", "children"),
    Output("optional-package-table", "children"),
    Output("trade-in-summary-table", "children"),
    Output("jac-motors-state-table", "children"),
    Input("date-filter", "start_date"),
    Input("date-filter", "end_date"),
    Input("state-filter", "value"),
    Input("form-filter", "value"),
    Input("order-badge-filter", "value"),
    Input("jac-state-filter", "value"),
    Input("combine-date-filter", "start_date"),
    Input("combine-date-filter", "end_date"),
)
def update_dashboard(start_date, end_date, states, forms, order_badges, jac_states, combine_start_date, combine_end_date):
    dff = filter_data(start_date, end_date, states, forms)
    weekly_source = filter_data(None, None, states, forms)
    weekly_dff, weekly_start, weekly_end = latest_week_data(weekly_source)
    order_dff = dff.copy()
    if order_badges and "Badge" in order_dff.columns:
        order_dff = order_dff[order_dff["Badge"].isin(order_badges)]

    total_leads = len(dff)
    date_min = dff["Date"].min()
    date_max = dff["Date"].max()
    date_text = "No data" if pd.isna(date_min) else f"{date_min:%d %b %Y} – {date_max:%d %b %Y}"
    total_card = metric_card("Total leads", f"{total_leads:,}")
    date_card = metric_card("Date range", date_text, "18px")

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

    location_counts = dff["Location"].value_counts().reset_index()
    location_counts.columns = ["Location", "Leads"]
    fig_location = px.bar(location_counts, x="Leads", y="Location", orientation="h", title="All Locations by Leads")
    fig_location.update_layout(
        yaxis={"categoryorder": "total ascending"},
        height=max(500, len(location_counts) * 28 + 120),
        margin=dict(l=20, r=20, t=55, b=20),
    )

    trade_counts = dff["Trade-in Clean"].dropna().astype("string").str.strip()
    trade_counts = trade_counts[trade_counts != ""].value_counts().reset_index()
    trade_counts.columns = ["Trade-in", "Leads"]
    fig_trade = px.bar(trade_counts, x="Trade-in", y="Leads", title="Trade-in Yes/No")
    fig_trade.update_layout(margin=dict(l=20, r=20, t=55, b=20))

    kpi_table = dealer_kpi_table(dff)
    weekly_summary = build_dealer_summary(weekly_dff)
    weekly_label = (
        "No dated data available"
        if weekly_start is None
        else f"Latest week: {weekly_start:%d %b %Y} to {weekly_end:%d %b %Y} | {len(weekly_dff):,} enquiries"
    )
    weekly_table = dealer_summary_table(weekly_summary)
    combine_dff = filter_data(combine_start_date, combine_end_date, [], [])
    jac_combined_summary = build_combined_destination_summary(combine_dff, "JAC Motors")
    jac_combined_detail = build_combined_destination_detail(combine_dff, "JAC Motors")
    combine_min = combine_dff["Date"].min()
    combine_max = combine_dff["Date"].max()
    moved_total = int(jac_combined_summary["Leads Moved"].sum()) if not jac_combined_summary.empty else 0
    destination_total = (
        int(jac_combined_summary["Destination Total Leads"].iloc[0])
        if not jac_combined_summary.empty
        else 0
    )
    combined_label = (
        "No dated data available"
        if pd.isna(combine_min)
        else f"Selected range: {combine_min:%d %b %Y} to {combine_max:%d %b %Y} | {moved_total:,} moved leads | JAC Motors total after combine: {destination_total:,}"
    )
    combined_table = combined_dealer_summary_table(jac_combined_summary)
    combined_detail_table = combined_dealer_detail_table(jac_combined_detail)
    registration_table = value_count_table(order_dff, "Registration Type", "Registration Type")
    badge_table = value_count_table(order_dff, "Badge", "Badge")
    colour_table = value_count_table(order_dff, "Colour", "Colour")
    second_preference_table = value_count_table(order_dff, "Second-preference Colour", "Second Preference")
    optional_package_table = optional_package_count_table(order_dff)
    trade_summary_table = trade_in_vehicle_table(order_dff)
    jac_state_table = jac_motors_state_table(dff, jac_states)

    return (
        total_card,
        date_card,
        fig_trend,
        fig_state,
        fig_form,
        fig_location,
        fig_trade,
        kpi_table,
        weekly_label,
        weekly_table,
        combined_label,
        combined_table,
        combined_detail_table,
        registration_table,
        badge_table,
        colour_table,
        second_preference_table,
        optional_package_table,
        trade_summary_table,
        jac_state_table,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False)
