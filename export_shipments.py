"""
Action Supply Chain Portal — Shipment Report Exporter
Exporteert appointment report als Excel, gefilterd op YTD.
Ondersteunt headless mode voor scheduled tasks.
"""

from playwright.sync_api import sync_playwright
from pathlib import Path
from datetime import date, datetime
from dotenv import load_dotenv
import os
import shutil
import subprocess
import sys
import time
import logging

load_dotenv()

# Paden
PROJECT_DIR = Path(__file__).parent
USER_DATA_DIR = PROJECT_DIR / "browser_profile"
DOWNLOAD_DIR = PROJECT_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)
DATA_DIR = PROJECT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR = PROJECT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "export.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# URLs
BASE_URL = "https://supplychainportal.action.eu"
REPORT_URL = f"{BASE_URL}/PAct/Report/AppointmentReportSupplier.aspx"

# Login IDs
LOGIN_USER = "ctl00_MainContent_LoginControl_TheLogin_UserName"
LOGIN_PASS = "ctl00_MainContent_LoginControl_TheLogin_Password"
LOGIN_REMEMBER = "ctl00_MainContent_LoginControl_TheLogin_RememberMe"
LOGIN_BTN = "ctl00_MainContent_LoginControl_TheLogin_Login"

# Filter IDs
DATE_FROM = "ctl00_MainContent_DataOverview_AppointmentReportFilterSupplier_FilterAppoinmentDate_DateFromToSelector_FromDateSelector_txtDate"
DATE_TO = "ctl00_MainContent_DataOverview_AppointmentReportFilterSupplier_FilterAppoinmentDate_DateFromToSelector_ToDateSelector_txtDate"
BTN_SEARCH = "ctl00_MainContent_DataOverview_btnQuickSearch"
BTN_EXPORT = "ctl00_MainContent_DataOverview_AppointmentReportExcelSupplier_theDataExcelDownload_theExcelBuildAsyncWithPoll_lbExcelExport"


def login_if_needed(page, headless):
    """Check of login nodig is en log automatisch in via .env credentials."""
    if "login" not in page.url.lower() and "AppointmentReportSupplier" in page.url:
        return

    gebruiker = os.getenv("ACTION_USER")
    wachtwoord = os.getenv("ACTION_PASS")

    if gebruiker and wachtwoord:
        log.info("Sessie verlopen — automatisch inloggen...")
        page.locator(f"#{LOGIN_USER}").fill(gebruiker)
        page.locator(f"#{LOGIN_PASS}").fill(wachtwoord)
        page.locator(f"#{LOGIN_REMEMBER}").check()
        page.locator(f"#{LOGIN_BTN}").click()
        page.wait_for_load_state("networkidle", timeout=30_000)

        if "login" in page.url.lower():
            log.error("Automatische login mislukt — controleer ACTION_USER en ACTION_PASS in .env")
            sys.exit(1)

        log.info("Ingelogd! Navigeren naar report...")
        page.goto(REPORT_URL, wait_until="networkidle", timeout=30_000)
    elif headless:
        log.error("Sessie verlopen en geen credentials in .env! Stel ACTION_USER en ACTION_PASS in.")
        sys.exit(1)
    else:
        log.info("Login nodig — log in via het browservenster (max 5 min)...")
        page.wait_for_function(
            """() => !window.location.href.toLowerCase().includes('login')""",
            timeout=300_000,
        )
        log.info("Ingelogd! Navigeren naar report...")
        page.goto(REPORT_URL, wait_until="networkidle", timeout=30_000)


def set_date_filter(page, from_date, to_date):
    """Vul het datumbereik in (formaat: yyyy-MM-dd)."""
    from_str = from_date.strftime("%Y-%m-%d")
    to_str = to_date.strftime("%Y-%m-%d")
    log.info(f"Datumfilter: {from_str} t/m {to_str}")

    from_field = page.locator(f"#{DATE_FROM}")
    from_field.click()
    from_field.fill("")
    from_field.type(from_str, delay=50)
    from_field.press("Tab")
    time.sleep(0.3)

    to_field = page.locator(f"#{DATE_TO}")
    to_field.click()
    to_field.fill("")
    to_field.type(to_str, delay=50)
    to_field.press("Tab")
    time.sleep(0.3)


def click_search(page):
    """Klik op Search en wacht op resultaten."""
    log.info("Zoeken...")
    page.locator(f"#{BTN_SEARCH}").click()
    page.wait_for_load_state("networkidle", timeout=60_000)
    time.sleep(1)
    log.info("Resultaten geladen.")


def export_to_excel(page):
    """Klik op Export to Excel en download het bestand."""
    log.info("Exporteren naar Excel...")
    export_link = page.locator(f"#{BTN_EXPORT}")
    export_link.scroll_into_view_if_needed()
    time.sleep(0.5)

    with page.expect_download(timeout=300_000) as download_info:
        export_link.click()
        log.info("Wachten op Excel-bestand...")
    download = download_info.value

    today = date.today().strftime("%Y-%m-%d")
    filename = f"AppointmentReport_{today}.xlsx"
    filepath = DOWNLOAD_DIR / filename
    download.save_as(filepath)
    log.info(f"Gedownload: {filepath}")
    return filepath


def push_naar_github(filepath: Path):
    """Kopieer bestand naar data/ map en push naar GitHub."""
    data_bestand = DATA_DIR / "AppointmentReport_latest.xlsx"
    shutil.copy2(filepath, data_bestand)
    log.info(f"Gekopieerd naar: {data_bestand}")

    try:
        subprocess.run(["git", "add", str(data_bestand)], cwd=PROJECT_DIR, check=True)
        datum = date.today().strftime("%Y-%m-%d")
        subprocess.run(
            ["git", "commit", "-m", f"Update rapport {datum}"],
            cwd=PROJECT_DIR, check=True,
        )
        subprocess.run(["git", "push"], cwd=PROJECT_DIR, check=True)
        log.info("Data gepusht naar GitHub — dashboard wordt automatisch bijgewerkt.")
    except subprocess.CalledProcessError as e:
        log.warning(f"Git push mislukt: {e}")


def main():
    headless = "--headless" in sys.argv

    today = date.today()
    from_date = date(2025, 12, 8)  # Start seizoen
    to_date = today

    log.info(f"Start export (headless={headless})")

    with sync_playwright() as pw:
        log.info("Browser starten...")
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=headless,
            viewport={"width": 1600, "height": 1000},
            locale="nl-NL",
            accept_downloads=True,
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            log.info("Navigeren naar report pagina...")
            page.goto(REPORT_URL, wait_until="networkidle", timeout=30_000)

            login_if_needed(page, headless)
            log.info(f"Pagina geladen: {page.url}")

            set_date_filter(page, from_date, to_date)
            click_search(page)
            filepath = export_to_excel(page)
            push_naar_github(filepath)

            log.info(f"Klaar! Bestand: {filepath}")
        except Exception as e:
            log.error(f"Fout: {e}")
            raise
        finally:
            context.close()


if __name__ == "__main__":
    main()
