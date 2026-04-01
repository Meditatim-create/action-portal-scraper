"""Vandaag — live overzicht van ritten met auto-refresh elke 10 minuten."""

import locale
import os
import subprocess
import time
from datetime import date, datetime, timedelta

# Nederlandse dag- en maandnamen
try:
    locale.setlocale(locale.LC_TIME, "nl_NL.UTF-8")
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, "Dutch_Netherlands.1252")
    except locale.Error:
        pass  # Fallback naar systeem-default

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from constanten import (
    DATA_PAD,
    ELHO_DONKER,
    ELHO_GROEN,
    GRIJS,
    ORANJE,
    REFRESH_INTERVAL,
    ROOD,
)

# ---------- Constanten ----------

BLAUW = "#3498db"
BRUIN = "#bb7339"
CRÈME = "#fafaf8"
TODAY_BESTAND = os.path.join(DATA_PAD, "AppointmentReport_today.xlsx")
DATUM_KOLOMMEN = [
    "Appointment", "Arrival", "Start unloading", "Finished unloading", "Cancel date",
]
NUMERIEKE_KOLOMMEN = ["Too late (min)", "Waiting (min)", "Unloading (min)", "Pallets"]

STATUS_VOLGORDE = {
    "Te laat": 0,
    "Op risico": 1,
    "Verwacht": 2,
    "Aangekomen": 3,
    "Bezig met lossen": 4,
    "Afgerond — te laat": 5,
    "Afgerond": 6,
    "Geannuleerd / NoShow": 7,
    "Overig": 8,
}

STATUS_KLEUREN = {
    "Afgerond": ELHO_GROEN,
    "Afgerond — te laat": BRUIN,
    "Aangekomen": BLAUW,
    "Bezig met lossen": BLAUW,
    "Verwacht": ELHO_DONKER,
    "Op risico": ORANJE,
    "Te laat": ROOD,
    "Geannuleerd / NoShow": GRIJS,
    "Overig": GRIJS,
}


# ---------- Data ophalen ----------

def _data_is_verouderd() -> bool:
    """Check of het today-bestand ouder is dan REFRESH_INTERVAL seconden."""
    if not os.path.exists(TODAY_BESTAND):
        return True
    leeftijd = time.time() - os.path.getmtime(TODAY_BESTAND)
    return leeftijd > REFRESH_INTERVAL


def _data_versheid() -> str | None:
    """Geef bestandstijd van het today-rapport."""
    if os.path.exists(TODAY_BESTAND):
        mtime = datetime.fromtimestamp(os.path.getmtime(TODAY_BESTAND))
        return mtime.strftime("%H:%M")
    return None


def _ververs_data() -> bool:
    """Draai quick_refresh als subprocess. Geeft True bij succes."""
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        result = subprocess.run(
            ["py", "export_shipments.py", "--quick", "--headless"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            st.error(f"Scraper fout: {result.stderr[-300:]}" if result.stderr else "Onbekende fout")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        st.error("Scraper timeout (>2 min). Mogelijk is de portal traag.")
        return False
    except FileNotFoundError:
        # Playwright niet geïnstalleerd (bijv. Streamlit Cloud)
        return False


def _laad_today_data() -> pd.DataFrame | None:
    """Laad het today Excel-bestand en verwerk kolommen."""
    if not os.path.exists(TODAY_BESTAND):
        return None
    try:
        df = pd.read_excel(TODAY_BESTAND, engine="openpyxl")
        for col in DATUM_KOLOMMEN:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        for col in NUMERIEKE_KOLOMMEN:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        for col in df.select_dtypes(include="object").columns:
            df[col] = df[col].str.strip()
        return df
    except Exception:
        return None


# ---------- Statuslogica ----------

def _bepaal_status(row, nu: datetime) -> str:
    """Bepaal de vandaag-status op basis van Inbound state, Time label en afspraaktijd."""
    state = row.get("Inbound state", "")
    appointment = row.get("Appointment")
    time_label = str(row.get("Time label", "")).strip()

    if state == "Finished":
        if time_label in ("Late", "Late - Reported"):
            return "Afgerond — te laat"
        return "Afgerond"
    if state == "Arrived":
        return "Aangekomen"
    if state == "Unloading":
        return "Bezig met lossen"
    if state in ("Cancelled", "NoShow"):
        return "Geannuleerd / NoShow"
    if state in ("Refused", "Removed", "Left"):
        return "Overig"

    # Expected of andere actieve status
    if pd.notna(appointment):
        minuten_over = (nu - appointment).total_seconds() / 60
        if minuten_over >= 30:
            # 30+ min na afspraak en nog geen aankomst
            return "Te laat"
        if minuten_over > 0:
            # Afspraaktijd gepasseerd maar nog binnen 30 min marge
            return "Op risico"
        if appointment < nu + timedelta(hours=1):
            # Afspraak binnen komend uur
            return "Op risico"
        return "Verwacht"

    return "Verwacht"


# ---------- UI componenten ----------

def _status_badge(status: str) -> str:
    """Gekleurde badge voor een status."""
    kleur = STATUS_KLEUREN.get(status, GRIJS)
    return (
        f'<span style="display:inline-block;background:{kleur}15;color:{kleur};'
        f'padding:2px 10px;border-radius:20px;font-size:0.78rem;font-weight:600;white-space:nowrap;">'
        f'{status}</span>'
    )


def _render_kpi_kaart(col, label: str, waarde: int, kleur: str, sublabel: str = ""):
    """KPI kaart in elho-stijl — compact en uitgelijnd."""
    sub = f'<div style="font-size:0.7rem;color:{BRUIN};margin-top:2px;min-height:1em;">{sublabel}</div>' if sublabel else '<div style="min-height:1em;"></div>'
    col.markdown(
        f'<div style="background:{CRÈME};border:1px solid {kleur}25;border-radius:14px;'
        f'padding:14px 12px 10px;text-align:center;">'
        f'<div style="font-size:0.75rem;color:{ELHO_DONKER}80;letter-spacing:0.04em;">{label}</div>'
        f'<div style="font-size:2.4rem;font-weight:700;color:{kleur};line-height:1.15;margin:2px 0;">{waarde}</div>'
        f'{sub}</div>',
        unsafe_allow_html=True,
    )


def _render_voortgang(afgerond: int, totaal: int):
    """Voortgangsbalk in elho-stijl."""
    pct = (afgerond / totaal * 100) if totaal > 0 else 0
    st.markdown(
        f"""
        <div style="margin: 16px 0 20px 0;">
            <div style="display: flex; justify-content: space-between; font-size: 0.8rem; color: {ELHO_DONKER}90; margin-bottom: 6px;">
                <span style="letter-spacing: 0.03em;">voortgang vandaag</span>
                <span style="font-weight: 600; color: {ELHO_DONKER};">{afgerond} / {totaal} ({pct:.0f}%)</span>
            </div>
            <div style="background: {ELHO_DONKER}12; border-radius: 10px; height: 10px; overflow: hidden;">
                <div style="background: linear-gradient(90deg, {ELHO_GROEN}, {ELHO_GROEN}cc); width: {pct:.0f}%; height: 100%; border-radius: 10px; transition: width 0.6s ease;"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_ritten_tabel(df_vandaag: pd.DataFrame, nu: datetime):
    """Tabel met alle ritten van vandaag, gesorteerd op urgentie."""
    if df_vandaag.empty:
        return

    df = df_vandaag.copy()
    df["Status"] = df.apply(_bepaal_status, axis=1, nu=nu)
    df["_sort"] = df["Status"].map(STATUS_VOLGORDE).fillna(99)
    df = df.sort_values(["_sort", "Appointment"], ascending=[True, True])

    # Vertraging kolom berekenen
    df["Vertraging"] = ""
    mask_laat = df["Status"] == "Te laat"
    if mask_laat.any():
        minuten_laat = ((nu - df.loc[mask_laat, "Appointment"]).dt.total_seconds() / 60).astype(int)
        df.loc[mask_laat, "Vertraging"] = minuten_laat.apply(lambda m: f"+{m} min")
    mask_afgerond_laat = df["Status"] == "Afgerond \u2014 te laat"
    if mask_afgerond_laat.any():
        df.loc[mask_afgerond_laat, "Vertraging"] = df.loc[mask_afgerond_laat, "Too late (min)"].apply(
            lambda m: f"+{int(m)} min" if pd.notna(m) else "te laat"
        )

    # Bouw rijen als lijst
    rijen = []
    td = "padding:8px 10px;"
    for _, rij in df.iterrows():
        status = rij["Status"]
        badge = _status_badge(status)
        ship_id = rij.get("Ship ID", "")
        owner = rij.get("Owner", "")
        dc = rij.get("DC", "")
        apt = rij["Appointment"].strftime("%H:%M") if pd.notna(rij.get("Appointment")) else ""
        arr = rij["Arrival"].strftime("%H:%M") if pd.notna(rij.get("Arrival")) else "\u2014"
        pal = int(rij["Pallets"]) if pd.notna(rij.get("Pallets")) else ""
        vertr = rij["Vertraging"]

        bg = ""
        if status == "Te laat":
            bg = f"background:{ROOD}08;"
        elif status == "Op risico":
            bg = f"background:{ORANJE}06;"
        elif "te laat" in status:
            bg = f"background:{BRUIN}06;"

        vkleur = ROOD if status == "Te laat" else BRUIN if vertr else ELHO_DONKER
        vhtml = f'<span style="color:{vkleur};font-weight:600;">{vertr}</span>' if vertr else ""

        rijen.append(
            f'<tr style="border-bottom:1px solid #eee;{bg}">'
            f'<td style="{td}">{badge}</td>'
            f'<td style="{td}font-family:monospace;font-size:0.82rem;">{ship_id}</td>'
            f'<td style="{td}">{owner}</td>'
            f'<td style="{td}font-weight:500;">{dc}</td>'
            f'<td style="{td}font-weight:600;">{apt}</td>'
            f'<td style="{td}color:{ELHO_DONKER}99;">{arr}</td>'
            f'<td style="{td}text-align:center;">{pal}</td>'
            f'<td style="{td}">{vhtml}</td>'
            f'</tr>'
        )

    body = "".join(rijen)
    th = f"padding:8px 10px;text-align:left;font-weight:500;font-size:0.73rem;letter-spacing:0.05em;color:{ELHO_DONKER}80;"

    html = (
        f'<div style="border-radius:12px;overflow:hidden;border:1px solid {ELHO_DONKER}12;">'
        f'<table style="width:auto;border-collapse:collapse;font-size:0.84rem;color:{ELHO_DONKER};table-layout:fixed;">'
        f'<colgroup>'
        f'<col style="width:140px;">'   # status
        f'<col style="width:80px;">'    # ship id
        f'<col style="width:130px;">'   # owner
        f'<col style="width:80px;">'    # dc
        f'<col style="width:55px;">'    # afspraak
        f'<col style="width:65px;">'    # aankomst
        f'<col style="width:50px;">'    # pallets
        f'<col style="width:80px;">'    # vertraging
        f'</colgroup>'
        f'<thead><tr style="background:{CRÈME};border-bottom:2px solid {ELHO_GROEN}40;">'
        f'<th style="{th}">status</th>'
        f'<th style="{th}">ship id</th>'
        f'<th style="{th}">owner</th>'
        f'<th style="{th}">dc</th>'
        f'<th style="{th}">afspraak</th>'
        f'<th style="{th}">aankomst</th>'
        f'<th style="{th}text-align:center;">pallets</th>'
        f'<th style="{th}">vertraging</th>'
        f'</tr></thead>'
        f'<tbody>{body}</tbody>'
        f'</table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# ---------- Pagina ----------

def render_vandaag():
    """Render de Vandaag-pagina met live data-refresh."""
    # Auto-refresh elke 10 minuten
    st_autorefresh(interval=REFRESH_INTERVAL * 1000, key="vandaag_refresh")

    nu = datetime.now()

    # --- Live data ophalen als verouderd ---
    verouderd = _data_is_verouderd()
    if verouderd:
        with st.spinner("🔄 Live data ophalen uit Action Portal..."):
            succes = _ververs_data()
            if not succes and not os.path.exists(TODAY_BESTAND):
                st.warning(
                    "Kon geen live data ophalen. Scraper is niet beschikbaar "
                    "(draai lokaal met Playwright geïnstalleerd)."
                )

    # --- Data laden ---
    df = _laad_today_data()

    # Header
    versheid = _data_versheid()
    versheid_tekst = f"data van {versheid}" if versheid else "geen data"

    st.markdown(
        f"""
        <div style="margin-bottom: 10px;">
            <h2 style="margin:0;color:{ELHO_DONKER};font-weight:700;letter-spacing:-0.02em;font-size:1.5rem;">
                vandaag — {nu.strftime('%A %d %B').lower()}
            </h2>
            <div style="display:flex;align-items:center;gap:8px;margin-top:6px;">
                <span style="
                    display:inline-block;
                    width:8px;height:8px;
                    border-radius:50%;
                    background:{'#4ade80' if not verouderd else ORANJE};
                "></span>
                <span style="font-size:0.8rem;color:{ELHO_DONKER}80;">
                    {versheid_tekst} · refresh elke {REFRESH_INTERVAL // 60} min
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Handmatige vernieuw-knop
    if st.button("🔄 nu verversen", key="vandaag_vernieuw"):
        with st.spinner("🔄 Data ophalen uit Action Portal..."):
            _ververs_data()
        st.rerun()

    # Geen data?
    if df is None or df.empty:
        st.warning(
            "Geen data beschikbaar. Controleer of de scraper draait "
            "(`py export_shipments.py --quick --headless`)."
        )
        return

    # Filter op vandaag
    if "Appointment" in df.columns:
        mask = df["Appointment"].dt.date == date.today()
        df_vandaag = df[mask].copy()
    else:
        df_vandaag = df.copy()

    if df_vandaag.empty:
        st.info(
            f"Geen ritten gevonden voor vandaag ({nu.strftime('%d-%m-%Y')}). "
            "Mogelijk zijn er vandaag geen leveringen gepland."
        )
        return

    # Statussen bepalen
    df_vandaag["Status"] = df_vandaag.apply(_bepaal_status, axis=1, nu=nu)

    afgerond_totaal = df_vandaag["Status"].isin(["Afgerond", "Afgerond — te laat"]).sum()
    afgerond_ok = (df_vandaag["Status"] == "Afgerond").sum()
    afgerond_laat = (df_vandaag["Status"] == "Afgerond — te laat").sum()
    lossen = df_vandaag["Status"].isin(["Bezig met lossen", "Aangekomen"]).sum()
    verwacht = df_vandaag["Status"].isin(["Verwacht", "Op risico"]).sum()
    te_laat = (df_vandaag["Status"] == "Te laat").sum()
    totaal = len(df_vandaag)

    # KPI kaarten
    c1, c2, c3, c4 = st.columns(4)
    sublabel_afgerond = f"waarvan {afgerond_laat}× te laat" if afgerond_laat else ""
    _render_kpi_kaart(c1, "afgerond", afgerond_totaal, ELHO_GROEN, sublabel_afgerond)
    _render_kpi_kaart(c2, "bezig met lossen", lossen, BLAUW)
    _render_kpi_kaart(c3, "verwacht", verwacht, ELHO_DONKER)
    _render_kpi_kaart(c4, "te laat / risico", te_laat, ROOD)

    # Voortgangsbalk
    _render_voortgang(afgerond_totaal, totaal)

    # Detailtabel
    _render_ritten_tabel(df_vandaag, nu)


# Streamlit page entry point
render_vandaag()
