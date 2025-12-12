from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException

from time import sleep, time
from datetime import datetime
import threading
import firebase_admin
from firebase_admin import credentials, db
import pytz
import os
import sys
import gc

# =============================================================
# 🔥 CONFIGURAÇÃO GERAL
# =============================================================
SERVICE_ACCOUNT_FILE = "serviceAccountKey.json"
DATABASE_URL = "https://history-dashboard-a70ee-default-rtdb.firebaseio.com"

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

TZ_BR = pytz.timezone("America/Sao_Paulo")

POLLING_INTERVAL = 0.05
TEMPO_MAX_INATIVIDADE = 360  # 6 minutos

IFRAME_XPATH = '//iframe[contains(@src,"spribe") or contains(@src,"aviator")]'
HIST_SELECTOR = "app-stats-widget, .payouts-block"
PAYOUT_SELECTOR = ".payout:first-child, .bubble-multiplier:first-child"

# =============================================================
# 🔥 FIREBASE
# =============================================================
if not firebase_admin._apps:
    cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
    firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})

# =============================================================
# 🧩 UTIL
# =============================================================
def getColorClass(v):
    v = float(v)
    if v < 2: return "blue-bg"
    if v < 10: return "purple-bg"
    return "magenta-bg"


def start_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.page_load_strategy = "eager"

    try:
        return webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
    except:
        return webdriver.Chrome(options=options)


def login(driver):
    driver.get("https://www.goathbet.com")
    sleep(4)

    try:
        driver.find_element(By.XPATH, "//button[contains(.,'Entrar')]").click()
        sleep(2)
        driver.find_element(By.NAME, "email").send_keys(EMAIL)
        driver.find_element(By.NAME, "password").send_keys(PASSWORD)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        sleep(6)
    except:
        pass


def init_game(driver, link):
    driver.get(link)
    sleep(5)

    iframe = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.XPATH, IFRAME_XPATH))
    )
    driver.switch_to.frame(iframe)

    hist = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, HIST_SELECTOR))
    )

    return iframe, hist


def capture_loop(nome, link, firebase_path):
    driver = None

    while True:
        try:
            driver = start_driver()
            login(driver)

            iframe, hist = init_game(driver, link)

            last_sent = None
            last_time = time()

            print(f"🚀 {nome} iniciado")

            while True:
                try:
                    payout = hist.find_element(By.CSS_SELECTOR, PAYOUT_SELECTOR)
                    raw = payout.text.lower().replace("x", "").strip()
                    if not raw:
                        continue

                    mult = float(raw)

                    if mult != last_sent:
                        now = datetime.now(TZ_BR)
                        payload = {
                            "multiplier": f"{mult:.2f}",
                            "time": now.strftime("%H:%M:%S"),
                            "date": now.strftime("%Y-%m-%d"),
                            "color": getColorClass(mult)
                        }
                        key = now.strftime("%Y-%m-%d_%H-%M-%S-%f")
                        db.reference(f"{firebase_path}/{key}").set(payload)

                        print(f"🔥 [{nome}] {payload['multiplier']}x")
                        last_sent = mult
                        last_time = time()

                except (StaleElementReferenceException, NoSuchElementException):
                    iframe, hist = init_game(driver, link)

                if time() - last_time > TEMPO_MAX_INATIVIDADE:
                    raise Exception("Inatividade")

                sleep(POLLING_INTERVAL)

        except Exception as e:
            print(f"♻️ Reiniciando {nome}: {e}")
            try:
                driver.quit()
            except:
                pass
            gc.collect()
            sleep(5)


# =============================================================
# 🚀 MAIN
# =============================================================
if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❌ Configure EMAIL e PASSWORD")
        sys.exit(1)

    t1 = threading.Thread(
        target=capture_loop,
        args=("AVIATOR 1", "https://www.goathbet.com/pt/casino/spribe/aviator", "history"),
        daemon=True
    )

    t2 = threading.Thread(
        target=capture_loop,
        args=("AVIATOR 2", "https://www.goathbet.com/pt/casino/spribe/aviator-2", "aviator2"),
        daemon=True
    )

    t1.start()
    t2.start()

    t1.join()
    t2.join()
