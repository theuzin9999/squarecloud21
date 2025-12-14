from __future__ import annotations

import os
import sys
import logging
import threading
import signal
from dataclasses import dataclass
from time import sleep, time
from datetime import datetime, date
from typing import Optional, Tuple, List

import pytz
import firebase_admin
from firebase_admin import credentials, db

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException

from webdriver_manager.chrome import ChromeDriverManager


SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "serviceAccountKey.json")
DATABASE_URL = os.getenv("DATABASE_URL", "https://history-dashboard-a70ee-default-rtdb.firebaseio.com")
URL_DO_SITE = os.getenv("URL_DO_SITE", "https://www.goathbet.com")

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

TZ_BR = pytz.timezone(os.getenv("TZ", "America/Sao_Paulo"))

POLLING_INTERVAL = float(os.getenv("POLLING_INTERVAL", "0.12"))
TEMPO_MAX_INATIVIDADE = int(os.getenv("TEMPO_MAX_INATIVIDADE", "360"))
DAILY_RESTART_WINDOW_MIN = int(os.getenv("DAILY_RESTART_WINDOW_MIN", "7"))
FLOAT_EPS = float(os.getenv("FLOAT_EPS", "0.0001"))

HEADLESS = os.getenv("HEADLESS", "1").strip() != "0"
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH")

logging.getLogger("WDM").setLevel(logging.ERROR)
os.environ["WDM_LOG_LEVEL"] = "0"

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper().strip()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("goathbot")

CONFIG_BOTS = [
    {
        "nome": "ORIGINAL",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator",
        "firebase_path": "history",
    },
    {
        "nome": "AVIATOR 2",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator-2",
        "firebase_path": "aviator2",
    },
]

STOP_EVENT = threading.Event()


def _handle_signal(sig, frame):
    STOP_EVENT.set()
    log.warning("Encerrando por sinal %s", sig)


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


def init_firebase() -> None:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})


def start_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    if HEADLESS:
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.page_load_strategy = "eager"
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--log-level=3")
    options.add_argument("--silent")

    if CHROMEDRIVER_PATH and os.path.exists(CHROMEDRIVER_PATH):
        return webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=options)

    try:
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except Exception:
        return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)


def safe_click(driver, by, value, timeout=5):
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        driver.execute_script("arguments[0].click();", el)
        return True
    except Exception:
        return False


def check_blocking_modals(driver):
    xpaths = [
        "//button[contains(., 'Sim')]",
        "//button[@data-age-action='yes']",
        "//button[contains(., 'Aceitar')]",
        "//button[contains(., 'Entendi')]",
        "//button[contains(., 'OK')]",
    ]
    for xp in xpaths:
        if safe_click(driver, By.XPATH, xp, timeout=1):
            break


def wait_for_iframe(driver, timeout=15):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located(
            (By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]')
        )
    )


def wait_for_history_element(driver, timeout=8):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block, app-stats-widget"))
    )


def process_login(driver, target_link):
    driver.get(URL_DO_SITE)
    sleep(2)
    check_blocking_modals(driver)

    safe_click(driver, By.XPATH, "//button[contains(., 'Entrar')]", 6)

    try:
        email_el = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.NAME, "email")))
        pass_el = driver.find_element(By.NAME, "password")
        email_el.clear()
        pass_el.clear()
        email_el.send_keys(EMAIL or "")
        pass_el.send_keys(PASSWORD or "")
        safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 6)
        sleep(3)
    except Exception:
        pass

    driver.get(target_link)
    sleep(3)
    check_blocking_modals(driver)


def initialize_game_elements(driver):
    driver.switch_to.default_content()
    iframe = wait_for_iframe(driver, 12)
    driver.switch_to.frame(iframe)
    hist = wait_for_history_element(driver, 10)
    return iframe, hist


def get_color_class(m):
    if 1.0 <= m < 2.0:
        return "blue-bg"
    if 2.0 <= m < 10.0:
        return "purple-bg"
    if m >= 10.0:
        return "magenta-bg"
    return "default-bg"


def floats_equal(a, b):
    return abs(a - b) <= FLOAT_EPS


def parse_multipliers(hist):
    results = []
    try:
        items = hist.find_elements(By.CSS_SELECTOR, ".payout, .bubble-multiplier")
        for it in items:
            txt = (it.text or "").replace("x", "").strip()
            try:
                v = float(txt)
                if v >= 1:
                    results.append(v)
            except Exception:
                pass
    except Exception:
        pass

    if not results:
        try:
            txt = hist.text.replace("x", " ").replace("\n", " ")
            for t in txt.split():
                try:
                    v = float(t)
                    if v >= 1:
                        results.append(v)
                except Exception:
                    pass
        except Exception:
            pass

    return results


@dataclass
class BotConfig:
    nome: str
    link: str
    firebase_path: str


def run_single_bot(cfg: BotConfig):
    relogin_date = date.today()

    while not STOP_EVENT.is_set():
        driver = None
        try:
            driver = start_driver()
            process_login(driver, cfg.link)
            _, hist = initialize_game_elements(driver)

            last_sent = None
            last_seen = time()

            while not STOP_EVENT.is_set():
                now = datetime.now(TZ_BR)

                if now.hour == 0 and now.minute <= DAILY_RESTART_WINDOW_MIN and relogin_date != now.date():
                    relogin_date = now.date()
                    driver.quit()
                    break

                if time() - last_seen > TEMPO_MAX_INATIVIDADE:
                    raise RuntimeError("Inatividade")

                try:
                    res = parse_multipliers(hist)
                    if res:
                        m = res[0]
                        if last_sent is None or not floats_equal(m, last_sent):
                            last_seen = time()
                            data = {
                                "multiplier": f"{m:.2f}",
                                "time": now.strftime("%H:%M:%S"),
                                "date": now.strftime("%Y-%m-%d"),
                                "color": get_color_class(m),
                            }
                            key = now.strftime("%Y-%m-%d_%H-%M-%S-%f") + "_" + cfg.nome.replace(" ", "_")
                            db.reference(f"{cfg.firebase_path}/{key}").set(data)
                            last_sent = m
                    sleep(POLLING_INTERVAL)
                except (StaleElementReferenceException, TimeoutException):
                    _, hist = initialize_game_elements(driver)

        except Exception:
            if driver:
                driver.quit()
            sleep(3)


def main():
    if not EMAIL or not PASSWORD:
        return 1

    init_firebase()

    threads = []
    for b in CONFIG_BOTS:
        t = threading.Thread(
            target=run_single_bot,
            args=(BotConfig(**b),),
            daemon=True,
        )
        t.start()
        threads.append(t)
        sleep(1)

    while not STOP_EVENT.is_set():
        sleep(1)


if __name__ == "__main__":
    sys.exit(main())
