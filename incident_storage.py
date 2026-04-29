"""Opslag van incident-reasons.

Strategie:
- Op Streamlit Cloud (geen git, ephemeral filesystem): schrijf via GitHub Contents API.
- Lokaal (geen [github] secret geconfigureerd): schrijf naar lokale data/reasons.json.

GitHub-token nodig in secrets.toml:
    [github]
    token = "ghp_..."   # PAT met contents:write
    repo = "Meditatim-create/action-portal-scraper"
"""

import base64
import json
import os
from datetime import datetime

import streamlit as st

from constanten import REASONS_PAD


def _github_config() -> tuple[str | None, str | None]:
    """Geef (token, repo) uit secrets, of (None, None) bij lokale dev."""
    try:
        gh = st.secrets["github"]
        return gh["token"], gh["repo"]
    except (KeyError, FileNotFoundError):
        return None, None


def _laad_van_github(token: str, repo: str) -> tuple[dict, str | None]:
    """Haal reasons.json + sha op van GitHub. Geeft ({}, None) als bestand nog niet bestaat."""
    import requests
    url = f"https://api.github.com/repos/{repo}/contents/data/reasons.json"
    r = requests.get(
        url,
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
        timeout=10,
    )
    if r.status_code == 404:
        return {}, None
    r.raise_for_status()
    payload = r.json()
    inhoud = base64.b64decode(payload["content"]).decode("utf-8")
    return json.loads(inhoud) if inhoud.strip() else {}, payload["sha"]


def _push_naar_github(reasons: dict, token: str, repo: str, sha: str | None, bericht: str) -> bool:
    """Schrijf reasons.json naar GitHub. Met sha = update, zonder = create."""
    import requests
    url = f"https://api.github.com/repos/{repo}/contents/data/reasons.json"
    inhoud = json.dumps(reasons, indent=2, ensure_ascii=False, sort_keys=True)
    encoded = base64.b64encode(inhoud.encode("utf-8")).decode()
    payload = {"message": bericht, "content": encoded}
    if sha:
        payload["sha"] = sha
    r = requests.put(
        url,
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
        json=payload,
        timeout=15,
    )
    return r.status_code in (200, 201)


def _laad_lokaal() -> dict:
    if os.path.exists(REASONS_PAD):
        with open(REASONS_PAD, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _schrijf_lokaal(reasons: dict) -> None:
    os.makedirs(os.path.dirname(REASONS_PAD), exist_ok=True)
    with open(REASONS_PAD, "w", encoding="utf-8") as f:
        json.dump(reasons, f, indent=2, ensure_ascii=False, sort_keys=True)


def laad_reasons() -> dict:
    """Laad alle reasons. Bron: GitHub als token aanwezig, anders lokale file."""
    token, repo = _github_config()
    if token and repo:
        try:
            reasons, _sha = _laad_van_github(token, repo)
            return reasons
        except Exception as e:
            st.warning(f"Kon reasons niet van GitHub laden ({e}). Lokale fallback gebruikt.")
    return _laad_lokaal()


def sla_reason_op(
    ship_id: str,
    gebruiker: str,
    categorie: str,
    toelichting: str,
    inbound_state: str,
) -> tuple[bool, str]:
    """Sla 1 reason op. Retourneert (succes, melding)."""
    nieuwe_entry = {
        "ship_id": str(ship_id),
        "categorie": categorie,
        "toelichting": toelichting.strip(),
        "ingevuld_door": gebruiker,
        "ingevuld_op": datetime.now().isoformat(timespec="seconds"),
        "inbound_state": inbound_state,
    }

    token, repo = _github_config()
    if token and repo:
        try:
            reasons, sha = _laad_van_github(token, repo)
            reasons[str(ship_id)] = nieuwe_entry
            ok = _push_naar_github(
                reasons, token, repo, sha,
                f"Incident reason: ship {ship_id} ({categorie})",
            )
            if ok:
                return True, "Opgeslagen op GitHub."
            return False, "GitHub push faalde (mogelijk conflict — probeer opnieuw)."
        except Exception as e:
            return False, f"GitHub-fout: {e}"

    # Lokale fallback
    reasons = _laad_lokaal()
    reasons[str(ship_id)] = nieuwe_entry
    _schrijf_lokaal(reasons)
    return True, "Lokaal opgeslagen (geen GitHub-token geconfigureerd)."
