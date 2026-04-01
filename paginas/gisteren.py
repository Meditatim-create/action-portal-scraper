"""Gisteren — samenvatting vorige werkdag voor escalatie of complimenten."""

import os
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from constanten import (
    DATA_PAD,
    DATUM_KOLOMMEN,
    ELHO_DONKER,
    ELHO_GROEN,
    GRIJS,
    NUMERIEKE_KOLOMMEN,
    ORANJE,
    ROOD,
    nl_datum,
)

# ---------- Constanten ----------

BRUIN = "#bb7339"
CRÈME = "#fafaf8"
LATEST_BESTAND = os.path.join(DATA_PAD, "AppointmentReport_latest.xlsx")


# ---------- Data ----------

def _vorige_werkdag() -> date:
    """Geeft de vorige werkdag (ma-vr)."""
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _laad_data(dag: date) -> pd.DataFrame | None:
    """Laad data uit latest bestand en filter op gegeven dag."""
    if not os.path.exists(LATEST_BESTAND):
        return None
    try:
        df = pd.read_excel(LATEST_BESTAND, engine="openpyxl")
        for col in DATUM_KOLOMMEN:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        for col in NUMERIEKE_KOLOMMEN:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        for col in df.select_dtypes(include="object").columns:
            df[col] = df[col].str.strip()
        mask = df["Appointment"].dt.date == dag
        return df[mask].copy()
    except Exception:
        return None


# ---------- Berekeningen ----------

def _bereken_stats(df: pd.DataFrame) -> dict:
    """Bereken samenvattingsstatistieken."""
    totaal = len(df)
    finished = df[df["Inbound state"] == "Finished"]
    cancelled = (df["Inbound state"] == "Cancelled").sum()
    noshow = (df["Inbound state"] == "NoShow").sum()
    removed = (df["Inbound state"] == "Removed").sum()

    # Time labels
    on_time = finished["Time label"].isin(["On time", "Early"]).sum()
    late = finished["Time label"].isin(["Late", "Late - Reported"]).sum()
    otd_pct = (on_time / (on_time + late) * 100) if (on_time + late) > 0 else 0

    # Slot performance
    slot_basis = len(finished) + cancelled + noshow
    slot_pct = (len(finished) / slot_basis * 100) if slot_basis > 0 else 0

    # Gemiddelde vertraging van te late ritten
    late_mins = finished.loc[
        finished["Time label"].isin(["Late", "Late - Reported"]), "Too late (min)"
    ].dropna()
    gem_vertraging = late_mins.mean() if not late_mins.empty else 0

    return {
        "totaal": totaal,
        "finished": len(finished),
        "on_time": on_time,
        "late": late,
        "cancelled": cancelled,
        "noshow": noshow,
        "removed": removed,
        "otd_pct": otd_pct,
        "slot_pct": slot_pct,
        "gem_vertraging": gem_vertraging,
    }


# ---------- UI ----------

def _metric(label: str, waarde: str, kleur: str = ELHO_DONKER) -> str:
    """Compacte metric als HTML."""
    return (
        f'<div style="text-align:center;">'
        f'<div style="font-size:0.7rem;color:{ELHO_DONKER}80;letter-spacing:0.04em;">{label}</div>'
        f'<div style="font-size:1.8rem;font-weight:700;color:{kleur};line-height:1.2;">{waarde}</div>'
        f'</div>'
    )


def _render_kpi_kaart(col, label: str, waarde: str, kleur: str, sublabel: str = ""):
    """KPI kaart — zelfde stijl als vandaag-pagina."""
    sub = f'<div style="font-size:0.7rem;color:{BRUIN};margin-top:2px;min-height:1em;">{sublabel}</div>' if sublabel else '<div style="min-height:1em;"></div>'
    col.markdown(
        f'<div style="background:{CRÈME};border:1px solid {kleur}25;border-radius:14px;'
        f'padding:14px 12px 10px;text-align:center;">'
        f'<div style="font-size:0.75rem;color:{ELHO_DONKER}80;letter-spacing:0.04em;">{label}</div>'
        f'<div style="font-size:2.4rem;font-weight:700;color:{kleur};line-height:1.15;margin:2px 0;">{waarde}</div>'
        f'{sub}</div>',
        unsafe_allow_html=True,
    )


def _render_samenvatting(stats: dict):
    """Render de KPI samenvatting."""
    otd_kleur = ELHO_GROEN if stats["otd_pct"] >= 95 else ORANJE if stats["otd_pct"] >= 85 else ROOD
    slot_kleur = ELHO_GROEN if stats["slot_pct"] >= 95 else ORANJE if stats["slot_pct"] >= 85 else ROOD
    noshow_cancel = stats["noshow"] + stats["cancelled"]

    c1, c2, c3, c4, c5 = st.columns(5)
    _render_kpi_kaart(c1, "ritten", str(stats["totaal"]), ELHO_DONKER)
    _render_kpi_kaart(c2, "afgerond", str(stats["finished"]), ELHO_GROEN)
    _render_kpi_kaart(c3, "on-time delivery", f'{stats["otd_pct"]:.0f}%', otd_kleur)
    _render_kpi_kaart(c4, "slot performance", f'{stats["slot_pct"]:.0f}%', slot_kleur)
    _render_kpi_kaart(c5, "no-show / cancel", str(noshow_cancel), ROOD if noshow_cancel > 0 else GRIJS)


def _render_detail_tabel(df: pd.DataFrame):
    """Compacte tabel met alle ritten."""
    if df.empty:
        return

    df = df.sort_values("Appointment")

    rijen = []
    td = "padding:7px 10px;"
    for _, rij in df.iterrows():
        state = rij.get("Inbound state", "")
        time_label = str(rij.get("Time label", "")).strip()
        too_late = rij.get("Too late (min)")

        # Status badge
        if state == "Finished" and time_label in ("Late", "Late - Reported"):
            kleur, label = BRUIN, "Afgerond — te laat"
        elif state == "Finished":
            kleur, label = ELHO_GROEN, "Afgerond"
        elif state == "NoShow":
            kleur, label = ROOD, "NoShow"
        elif state == "Cancelled":
            kleur, label = ROOD, "Geannuleerd"
        elif state == "Removed":
            kleur, label = GRIJS, "Removed"
        else:
            kleur, label = GRIJS, state

        badge = (
            f'<span style="display:inline-block;background:{kleur}15;color:{kleur};'
            f'padding:2px 10px;border-radius:20px;font-size:0.78rem;font-weight:600;white-space:nowrap;">'
            f'{label}</span>'
        )

        apt = rij["Appointment"].strftime("%H:%M") if pd.notna(rij.get("Appointment")) else ""
        arr = rij["Arrival"].strftime("%H:%M") if pd.notna(rij.get("Arrival")) else "\u2014"
        owner = rij.get("Owner", "")
        dc = rij.get("DC", "")
        pal = int(rij["Pallets"]) if pd.notna(rij.get("Pallets")) else ""

        vertr = ""
        if pd.notna(too_late) and too_late > 0:
            vkleur = BRUIN if state == "Finished" else ROOD
            vertr = f'<span style="color:{vkleur};font-weight:600;">+{int(too_late)} min</span>'

        bg = ""
        if label == "laat":
            bg = f"background:{BRUIN}06;"
        elif label in ("no-show", "cancel"):
            bg = f"background:{ROOD}06;"

        rijen.append(
            f'<tr style="border-bottom:1px solid #eee;{bg}">'
            f'<td style="{td}">{badge}</td>'
            f'<td style="{td}font-weight:600;">{apt}</td>'
            f'<td style="{td}font-family:monospace;font-size:0.82rem;">{rij.get("Ship ID", "")}</td>'
            f'<td style="{td}">{owner}</td>'
            f'<td style="{td}font-weight:500;">{dc}</td>'
            f'<td style="{td}text-align:center;">{pal}</td>'
            f'<td style="{td}">{vertr}</td>'
            f'</tr>'
        )

    body = "".join(rijen)
    th = f"padding:8px 10px;text-align:left;font-weight:500;font-size:0.73rem;letter-spacing:0.05em;color:{ELHO_DONKER}80;"

    html = (
        f'<div style="border-radius:12px;overflow:hidden;border:1px solid {ELHO_DONKER}12;">'
        f'<table style="width:auto;border-collapse:collapse;font-size:0.84rem;color:{ELHO_DONKER};table-layout:fixed;">'
        f'<colgroup>'
        f'<col style="width:140px;">'   # status
        f'<col style="width:50px;">'    # tijd
        f'<col style="width:80px;">'    # ship id
        f'<col style="width:130px;">'   # owner
        f'<col style="width:80px;">'    # dc
        f'<col style="width:35px;">'    # pal
        f'<col style="width:75px;">'    # vertraging
        f'</colgroup>'
        f'<thead><tr style="background:{CRÈME};border-bottom:2px solid {ELHO_GROEN}40;">'
        f'<th style="{th}">status</th>'
        f'<th style="{th}">tijd</th>'
        f'<th style="{th}">ship id</th>'
        f'<th style="{th}">owner</th>'
        f'<th style="{th}">dc</th>'
        f'<th style="{th}text-align:center;">pal</th>'
        f'<th style="{th}">vertraging</th>'
        f'</tr></thead>'
        f'<tbody>{body}</tbody>'
        f'</table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def _render_escalatie(df: pd.DataFrame, stats: dict):
    """Toon escalatie- en complimentenpunten."""
    items = []

    # Complimenten
    if stats["otd_pct"] >= 95:
        items.append(("compliment", f'OTD van {stats["otd_pct"]:.0f}% — uitstekende dag!'))
    if stats["slot_pct"] >= 95 and stats["noshow"] == 0:
        items.append(("compliment", "Geen no-shows — goede planning."))

    # Escalaties
    if stats["otd_pct"] < 85:
        items.append(("escalatie", f'OTD slechts {stats["otd_pct"]:.0f}% — structureel te laat.'))
    if stats["noshow"] > 0:
        noshow_ritten = df[df["Inbound state"] == "NoShow"]
        dcs = ", ".join(noshow_ritten["DC"].unique())
        items.append(("escalatie", f'{stats["noshow"]}× no-show ({dcs}) — opvolging nodig.'))
    if stats["cancelled"] > 0:
        items.append(("aandacht", f'{stats["cancelled"]}× geannuleerd — reden checken.'))

    # Te late ritten benoemen
    late_ritten = df[(df["Inbound state"] == "Finished") & df["Time label"].isin(["Late", "Late - Reported"])]
    if not late_ritten.empty:
        for _, rij in late_ritten.iterrows():
            mins = int(rij["Too late (min)"]) if pd.notna(rij.get("Too late (min)")) else "?"
            dc = rij.get("DC", "?")
            apt = rij["Appointment"].strftime("%H:%M") if pd.notna(rij.get("Appointment")) else "?"
            if isinstance(mins, int) and mins >= 60:
                items.append(("escalatie", f'Rit {apt} naar {dc}: +{mins} min te laat — escaleren.'))
            elif isinstance(mins, int) and mins >= 30:
                items.append(("aandacht", f'Rit {apt} naar {dc}: +{mins} min vertraging.'))

    if not items:
        st.markdown(
            f'<div style="padding:16px;background:{ELHO_GROEN}10;border-radius:12px;color:{ELHO_DONKER};">'
            f'Geen bijzonderheden — alles op orde.</div>',
            unsafe_allow_html=True,
        )
        return

    iconen = {"compliment": "👏", "escalatie": "🚨", "aandacht": "⚠️"}
    kleuren = {"compliment": ELHO_GROEN, "escalatie": ROOD, "aandacht": ORANJE}

    html_items = []
    for soort, tekst in items:
        icoon = iconen.get(soort, "•")
        kleur = kleuren.get(soort, GRIJS)
        html_items.append(
            f'<div style="display:flex;align-items:flex-start;gap:8px;padding:8px 0;'
            f'border-bottom:1px solid {ELHO_DONKER}08;">'
            f'<span style="font-size:1rem;flex-shrink:0;">{icoon}</span>'
            f'<span style="color:{kleur};font-size:0.85rem;font-weight:500;">{tekst}</span>'
            f'</div>'
        )

    st.markdown(
        f'<div style="background:{CRÈME};border-radius:12px;border:1px solid {ELHO_DONKER}10;padding:12px 16px;">'
        + "".join(html_items)
        + '</div>',
        unsafe_allow_html=True,
    )


# ---------- Pagina ----------

def render_gisteren():
    """Render de Gisteren-pagina."""
    dag = _vorige_werkdag()

    st.markdown(
        f"""
        <div style="margin-bottom: 10px;">
            <h2 style="margin:0;color:{ELHO_DONKER};font-weight:700;letter-spacing:-0.02em;font-size:1.5rem;">
                gisteren \u2014 {nl_datum(dag)}
            </h2>
            <div style="display:flex;align-items:center;gap:8px;margin-top:6px;">
                <span style="font-size:0.8rem;color:{ELHO_DONKER}80;">
                    samenvatting vorige werkdag \u00b7 escalatie & complimenten
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    df = _laad_data(dag)

    if df is None or df.empty:
        st.info(
            f"Geen data gevonden voor {dag.strftime('%d-%m-%Y')}. "
            "Controleer of het seizoensrapport up-to-date is."
        )
        return

    stats = _bereken_stats(df)

    # KPI rij
    _render_samenvatting(stats)

    st.markdown("")

    # Escalatie / complimenten
    st.markdown(
        f'<div style="font-size:0.85rem;font-weight:600;color:{ELHO_DONKER};margin:16px 0 8px;">actiepunten</div>',
        unsafe_allow_html=True,
    )
    _render_escalatie(df, stats)

    # Detail tabel
    st.markdown(
        f'<div style="font-size:0.85rem;font-weight:600;color:{ELHO_DONKER};margin:24px 0 8px;">alle ritten</div>',
        unsafe_allow_html=True,
    )
    _render_detail_tabel(df)


# Streamlit page entry point
render_gisteren()
