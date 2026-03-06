"""Action Portal Dashboard — Shipment Performance Analyse voor Elho B.V."""

import glob
import os
import re
from datetime import date, timedelta
from io import BytesIO

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---------- Configuratie ----------

DATA_PAD = os.path.join(os.path.dirname(__file__), "data")
DOWNLOADS_PAD = os.path.join(os.path.dirname(__file__), "downloads")

DATUM_KOLOMMEN = [
    "Appointment", "Arrival", "Start unloading", "Finished unloading", "Cancel date",
]

NUMERIEKE_KOLOMMEN = ["Too late (min)", "Waiting (min)", "Unloading (min)", "Pallets"]

TIME_LABEL_GOED = ["Early", "On time"]
TIME_LABEL_SLECHT = ["Late", "Late - Reported"]

ONZE_PERFORMANCE_STATES = ["Finished", "Cancelled", "NoShow"]
SLECHT_STATES = ["Cancelled", "NoShow"]

# Elho branding
ELHO_GROEN = "#76a73a"
ELHO_DONKER = "#0a4a2f"
ROOD = "#e74c3c"
GRIJS = "#95a5a6"
ORANJE = "#e67e22"


# ---------- Data laden ----------

def verwerk_excel(bestand) -> pd.DataFrame:
    """Lees en verwerk een AppointmentReport Excel bestand."""
    df = pd.read_excel(bestand)
    df.columns = df.columns.str.strip()

    for kolom in DATUM_KOLOMMEN:
        if kolom in df.columns:
            df[kolom] = pd.to_datetime(df[kolom], errors="coerce")

    for kolom in NUMERIEKE_KOLOMMEN:
        if kolom in df.columns:
            df[kolom] = pd.to_numeric(df[kolom], errors="coerce")

    if "Time label" in df.columns:
        df["Time label"] = df["Time label"].str.strip().replace("", pd.NA)

    if "Inbound state" in df.columns:
        df["Inbound state"] = df["Inbound state"].str.strip().replace("", pd.NA)

    return df


# ---------- Hulpfuncties ----------

def week_label(datum: pd.Timestamp) -> str:
    """Geeft 'W03-2026' formaat."""
    if pd.isna(datum):
        return "Onbekend"
    return f"W{datum.isocalendar()[1]:02d}-{datum.isocalendar()[0]}"


def _render_kpi_header(titel: str, pct: float, totaal: int, subtitel: str):
    """KPI header blok."""
    kleur = ELHO_GROEN if pct >= 95 else ROOD
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, {kleur}20, {kleur}05);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            margin-bottom: 10px;
        ">
            <div style="font-size: 1rem; color: #666;">{titel}</div>
            <div style="font-size: 3rem; font-weight: bold; color: {kleur};">{pct:.1f}%</div>
            <div style="font-size: 0.85rem; color: #999;">{totaal} shipments — {subtitel}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _metric_card_grijs(col, label: str, waarde: int, hint: str):
    """Metric in grijs — niet onze performance."""
    col.markdown(
        f"""
        <div style="
            background: {GRIJS}15;
            border-left: 4px solid {GRIJS};
            border-radius: 8px;
            padding: 12px;
            text-align: center;
            opacity: 0.7;
        ">
            <div style="font-size: 0.75rem; color: #666;">{label}</div>
            <div style="font-size: 1.8rem; font-weight: bold; color: {GRIJS};">{waarde}</div>
            <div style="font-size: 0.65rem; color: #999;">{hint}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------- Filters ----------

def _vorige_werkweek():
    """Bereken maandag en vrijdag van de vorige werkweek."""
    vandaag = date.today()
    # Maandag van deze week, dan 7 dagen terug = maandag vorige week
    maandag = vandaag - timedelta(days=vandaag.weekday() + 7)
    vrijdag = maandag + timedelta(days=4)
    return maandag, vrijdag


def _render_filters(df: pd.DataFrame):
    """Sidebar filters."""
    st.sidebar.header("Filters")

    if "Owner" in df.columns:
        owners = sorted(df["Owner"].dropna().unique())
        st.sidebar.multiselect("Owner (DSV / Goods)", owners, key="action_owner_filter")

    if "DC" in df.columns:
        dcs = sorted(df["DC"].dropna().unique())
        st.sidebar.multiselect("DC (distributiecentrum)", dcs, key="action_dc_filter")

    if "Appointment" in df.columns:
        datum_vals = df["Appointment"].dropna()
        if not datum_vals.empty:
            min_d = datum_vals.min().date()
            max_d = datum_vals.max().date()
            vw_van, vw_tot = _vorige_werkweek()
            # Begrens standaardwaarden tot beschikbare data
            default_van = max(vw_van, min_d)
            default_tot = min(vw_tot, max_d)

            st.sidebar.date_input("Van", value=default_van, min_value=min_d, max_value=max_d, key="action_datum_van")
            st.sidebar.date_input("Tot", value=default_tot, min_value=min_d, max_value=max_d, key="action_datum_tot")

            if st.sidebar.button("Toon alles"):
                st.session_state.action_datum_van = min_d
                st.session_state.action_datum_tot = max_d
                st.rerun()


def _pas_filters_toe(df: pd.DataFrame) -> pd.DataFrame:
    """Pas filters toe."""
    mask = pd.Series(True, index=df.index)

    geselecteerde_owners = st.session_state.get("action_owner_filter", [])
    if geselecteerde_owners:
        mask &= df["Owner"].isin(geselecteerde_owners)

    geselecteerde_dcs = st.session_state.get("action_dc_filter", [])
    if geselecteerde_dcs:
        mask &= df["DC"].isin(geselecteerde_dcs)

    if "Appointment" in df.columns:
        datum_van = st.session_state.get("action_datum_van")
        datum_tot = st.session_state.get("action_datum_tot")
        if datum_van is not None:
            mask &= df["Appointment"].dt.date >= datum_van
        if datum_tot is not None:
            mask &= df["Appointment"].dt.date <= datum_tot

    return df[mask]


# ---------- Charts ----------

def _render_dc_barchart(df: pd.DataFrame, tel_late_mee: bool):
    """Barchart: slot performance % per distributiecentrum."""
    st.subheader("Slot Performance per DC")

    if "DC" not in df.columns:
        st.info("Geen DC-data beschikbaar.")
        return

    dc_groups = []
    for dc, groep in df.groupby("DC"):
        totaal = len(groep)
        finished = (groep["Inbound state"] == "Finished").sum()

        if tel_late_mee:
            goed = groep["Time label"].isin(TIME_LABEL_GOED).sum()
            slecht = totaal - goed
        else:
            goed = finished
            slecht = totaal - finished

        pct = (goed / totaal * 100) if totaal > 0 else 0
        dc_groups.append({"DC": dc, "pct": round(pct, 1), "totaal": totaal})

    dc_stats = pd.DataFrame(dc_groups).sort_values("pct", ascending=True)
    kleuren = [ELHO_GROEN if pct >= 95 else ROOD for pct in dc_stats["pct"]]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=dc_stats["DC"],
        x=dc_stats["pct"],
        orientation="h",
        marker_color=kleuren,
        text=[f"{v:.0f}% ({t})" for v, t in zip(dc_stats["pct"], dc_stats["totaal"])],
        textposition="outside",
    ))
    fig.add_vline(x=95, line_dash="dash", line_color=ELHO_DONKER, annotation_text="Target 95%")
    fig.update_layout(
        xaxis=dict(title="%", range=[0, 110]),
        height=max(350, len(dc_stats) * 28),
        margin=dict(l=10, r=10, t=10, b=30),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_pie_chart(df: pd.DataFrame):
    """Pie chart: verdeling Inbound state."""
    st.subheader("Inbound State Verdeling")

    if "Inbound state" not in df.columns:
        return

    verdeling = df["Inbound state"].value_counts().reset_index()
    verdeling.columns = ["Inbound state", "Aantal"]

    kleur_map = {
        "Finished": ELHO_GROEN,
        "Cancelled": ROOD,
        "NoShow": ORANJE,
        "Refused": GRIJS,
        "Removed": GRIJS,
    }
    kleuren = [kleur_map.get(state, GRIJS) for state in verdeling["Inbound state"]]

    fig = go.Figure(go.Pie(
        labels=verdeling["Inbound state"],
        values=verdeling["Aantal"],
        marker=dict(colors=kleuren),
        textinfo="label+percent+value",
        hole=0.3,
    ))
    fig.update_layout(
        height=350,
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_trend_chart(df: pd.DataFrame, tel_late_mee: bool):
    """Trend chart: slot performance % per week."""
    st.subheader("Slot Performance Trend per Week")

    if "Appointment" not in df.columns:
        st.info("Geen trenddata beschikbaar.")
        return

    df_trend = df.copy()
    df_trend["week"] = df_trend["Appointment"].apply(week_label)
    df_trend = df_trend[df_trend["week"] != "Onbekend"]

    if df_trend.empty:
        st.info("Geen geldige datums voor trendberekening.")
        return

    trend_groups = []
    for week, groep in df_trend.groupby("week"):
        totaal = len(groep)
        if tel_late_mee:
            goed = groep["Time label"].isin(TIME_LABEL_GOED).sum()
        else:
            goed = (groep["Inbound state"] == "Finished").sum()
        pct = (goed / totaal * 100) if totaal > 0 else 0
        trend_groups.append({"week": week, "pct": round(pct, 1), "totaal": totaal})

    trend = pd.DataFrame(trend_groups).sort_values("week")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=trend["week"],
        y=trend["pct"],
        mode="lines+markers",
        name="Slot Performance %",
        line=dict(color=ELHO_GROEN, width=2),
        marker=dict(size=8),
        text=[f"{t} shipments" for t in trend["totaal"]],
        hovertemplate="%{x}<br>%{y:.1f}%<br>%{text}<extra></extra>",
    ))
    fig.add_hline(y=95, line_dash="dash", line_color=ROOD, annotation_text="Target 95%")
    fig.update_layout(
        xaxis_title="Week",
        yaxis_title="%",
        yaxis=dict(range=[0, 105]),
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_detail_tabel(df: pd.DataFrame):
    """Volledige shipment data tabel."""
    st.subheader("Alle Shipments")

    toon_kolommen = [
        "Owner", "Ship ID", "PO NO", "DC", "Inbound state",
        "Appointment", "Time label", "Arrival",
        "Too late (min)", "Waiting (min)", "Unloading (min)",
        "Pallets", "Zone", "Reported issue", "Refusal reason",
    ]
    beschikbaar = [k for k in toon_kolommen if k in df.columns]

    st.dataframe(
        df[beschikbaar].sort_values("Appointment", ascending=False, na_position="last"),
        use_container_width=True,
        hide_index=True,
        height=500,
    )


# ---------- Hoofdpagina ----------

def render_dashboard(df: pd.DataFrame):
    """Render het volledige dashboard."""
    if df is None or df.empty:
        st.warning("Geen Action Portal data beschikbaar.")
        return

    _render_filters(df)
    df = _pas_filters_toe(df)

    if df.empty:
        st.warning("Geen shipments gevonden voor de geselecteerde filters.")
        return

    # === Slot Performance ===
    df_onze = df[df["Inbound state"].isin(ONZE_PERFORMANCE_STATES)].copy()
    totaal_onze = len(df_onze)
    finished = (df_onze["Inbound state"] == "Finished").sum()
    cancelled = (df_onze["Inbound state"] == "Cancelled").sum()
    noshow = (df_onze["Inbound state"] == "NoShow").sum()
    slot_pct = (finished / totaal_onze * 100) if totaal_onze > 0 else 0

    refused = (df["Inbound state"] == "Refused").sum()
    removed = (df["Inbound state"] == "Removed").sum()

    # OTD van finished shipments
    df_finished = df_onze[df_onze["Inbound state"] == "Finished"].copy()
    df_met_label = df_finished[df_finished["Time label"].notna()].copy()
    totaal_met_label = len(df_met_label)
    op_tijd = df_met_label["Time label"].isin(TIME_LABEL_GOED).sum() if totaal_met_label > 0 else 0
    te_laat = df_met_label["Time label"].isin(TIME_LABEL_SLECHT).sum() if totaal_met_label > 0 else 0
    otd_pct = (op_tijd / totaal_met_label * 100) if totaal_met_label > 0 else 0

    # Toggle
    tel_late_mee = st.checkbox(
        "Late shipments ook als 'slecht' meetellen in Slot Performance",
        value=False,
        key="action_tel_late_mee",
    )

    if tel_late_mee and totaal_met_label > 0:
        goed_slot = op_tijd
        slecht_slot = cancelled + noshow + te_laat
        totaal_slot = goed_slot + slecht_slot
        slot_pct = (goed_slot / totaal_slot * 100) if totaal_slot > 0 else 0

    # KPI headers
    col_slot, col_otd = st.columns(2)
    with col_slot:
        _render_kpi_header("Slot Performance", slot_pct, totaal_onze,
                           "Finished vs Cancelled + NoShow" + (" + Late" if tel_late_mee else ""))
    with col_otd:
        _render_kpi_header("OTD (Finished)", otd_pct, totaal_met_label,
                           "Early + On time vs Late")

    # Metric cards
    st.markdown("---")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Finished", finished)
    c2.metric("Cancelled", cancelled)
    c3.metric("NoShow", noshow)
    _metric_card_grijs(c4, "Refused", refused, "Door Action")
    _metric_card_grijs(c5, "Removed", removed, "Gepland")

    st.markdown("---")

    # Charts
    col_links, col_rechts = st.columns([3, 2])
    with col_links:
        _render_dc_barchart(df_onze, tel_late_mee)
    with col_rechts:
        _render_pie_chart(df)

    st.markdown("---")

    # Trend
    _render_trend_chart(df_onze, tel_late_mee)

    st.markdown("---")

    # Excel export
    def _maak_excel():
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Action Portal")
        return output.getvalue()

    st.download_button(
        "📥 Download gefilterde data (Excel)",
        data=_maak_excel(),
        file_name="action_portal_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # Detail tabel
    _render_detail_tabel(df)


# ---------- App ----------

st.set_page_config(
    page_title="Action Portal — Elho",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 10px;">
        <h1 style="margin: 0; color: #0a4a2f;">🚛 action portal</h1>
        <span style="color: #76a73a; font-size: 1.1rem;">elho b.v.</span>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------- Wachtwoord check ----------

def check_login() -> bool:
    """Toon login formulier en controleer gebruikersnaam + wachtwoord."""
    if st.session_state.get("ingelogd"):
        return True

    # Gebruikers uit secrets laden
    try:
        gebruikers = st.secrets["gebruikers"]
    except (KeyError, FileNotFoundError):
        # Geen secrets = development mode, geen login nodig
        return True

    st.markdown(
        f"""
        <div style="
            max-width: 400px;
            margin: 80px auto;
            padding: 40px;
            background: linear-gradient(135deg, {ELHO_GROEN}15, {ELHO_DONKER}05);
            border-radius: 16px;
            text-align: center;
        ">
            <div style="font-size: 3rem;">🔒</div>
            <div style="font-size: 1.2rem; color: {ELHO_DONKER}; margin: 10px 0;">
                Log in om het dashboard te bekijken
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("login_form"):
        gebruikersnaam = st.text_input("Gebruikersnaam")
        wachtwoord = st.text_input("Wachtwoord", type="password")
        verzonden = st.form_submit_button("Inloggen")

        if verzonden:
            if gebruikersnaam in gebruikers and gebruikers[gebruikersnaam] == wachtwoord:
                st.session_state.ingelogd = True
                st.session_state.gebruiker = gebruikersnaam
                st.rerun()
            else:
                st.error("Onjuiste gebruikersnaam of wachtwoord.")

    return False


if not check_login():
    st.stop()

# Data laden: data/ map (cloud) → downloads/ map (lokaal) → file uploader (fallback)
if "df_action" not in st.session_state:
    st.session_state.df_action = None

def _laad_automatisch():
    """Probeer data automatisch te laden uit data/ of downloads/ map."""
    # 1. data/ map (Streamlit Cloud — gepusht door scraper)
    latest = os.path.join(DATA_PAD, "AppointmentReport_latest.xlsx")
    if os.path.exists(latest):
        return verwerk_excel(latest), "cloud"

    # 2. downloads/ map (lokaal development)
    pattern = os.path.join(DOWNLOADS_PAD, "AppointmentReport_*.xlsx")
    bestanden = glob.glob(pattern)
    if bestanden:
        datum_re = re.compile(r"AppointmentReport_(\d{4}-\d{2}-\d{2})\.xlsx$")
        bestanden_met_datum = []
        for pad in bestanden:
            m = datum_re.search(os.path.basename(pad))
            if m:
                bestanden_met_datum.append((m.group(1), pad))
        if bestanden_met_datum:
            bestanden_met_datum.sort(reverse=True)
            return verwerk_excel(bestanden_met_datum[0][1]), "lokaal"

    return None, None

if st.session_state.df_action is None:
    st.session_state.df_action, bron = _laad_automatisch()

if st.session_state.df_action is not None:
    render_dashboard(st.session_state.df_action)
else:
    st.info("Geen data gevonden. Controleer of het rapport is gesynchroniseerd.")
