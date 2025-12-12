from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException
from time import sleep, time
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, db
import os
import pytz
import threading
import sys
import subprocess
import traceback
from queue import Queue

# =============================================================
# 🔒 CONTROLE GLOBAL
# =============================================================
DRIVER_LOCK = threading.Lock()
STOP_EVENT = threading.Event()

# =============================================================
# 🔥 CONFIGURAÇÕES
# =============================================================
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"

CONFIG_BOTS = [
    {"nome": "ORIGINAL", "link": "https://www.goathbet.com/pt/casino/spribe/aviator", "firebase_path": "history"},
    {"nome": "AVIATOR 2", "link": "https://www.goathbet.com/pt/casino/spribe/aviator-2", "firebase_path": "aviator2"}
]

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

TZ_BR = pytz.timezone("America/Sao_Paulo")
POLLING_INTERVAL = 0.1
TEMPO_MAX_INATIVIDADE = 360

# =============================================================
# 🔥 FIREBASE (FILA SEGURA)
# =============================================================
firebase_queue = Queue(maxsize=1000)

def firebase_worker():
    while True:
        path, data, nome = firebase_queue.get()
        try:
            key = datetime.now(TZ_BR).strftime("%Y-%m-%d_%H-%M-%S-%f")
            db.reference(f"{path}/{key}").set(data)
            print(f"🔥 [{nome}] {data['multiplier']}x às {data['time']}")
        except Exception:
            pass
        finally:
            firebase_queue.task_done()

threading.Thread(target=firebase_worker, daemon=True).start()

# =============================================================
# 🔧 FIREBASE INIT
# =============================================================
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
    print("✅ Firebase conectado.")
except Exception as e:
    print(f"❌ Firebase falhou: {e}")
    sys.exit()

# =============================================================
# 🧠 UTIL
# =============================================================
def getColorClass(value):
    if 1 <= value < 2: return "blue-bg"
    if 2 <= value < 10: return "purple-bg"
    if value >= 10: return "magenta-bg"
    return "default-bg"

# =============================================================
# 🚀 DRIVER
# =============================================================
def initialize_driver():
    try:
        subprocess.run("pkill chrome", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run("pkill chromedriver", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except: pass

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    try:
        return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)
    except:
        return webdriver.Chrome(options=options)

# =============================================================
# 🔑 LOGIN + ABAS
# =============================================================
def setup_tabs(driver):
    driver.get(URL_DO_SITE)
    sleep(3)

    try:
        driver.find_element(By.NAME, "email").send_keys(EMAIL)
        driver.find_element(By.NAME, "password").send_keys(PASSWORD)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        sleep(5)
    except: pass

    handles = {}
    for cfg in CONFIG_BOTS:
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])
        driver.get(cfg["link"])
        sleep(5)
        handles[cfg["firebase_path"]] = driver.current_window_handle

    return handles

# =============================================================
# 🎮 LOOP
# =============================================================
def start_bot(driver, cfg, handle):
    LAST = None
    LAST_TIME = time()

    while not STOP_EVENT.is_set():
        with DRIVER_LOCK:
            try:
                driver.switch_to.window(handle)
                iframe = driver.find_element(By.XPATH, '//iframe[contains(@src,"spribe")]')
                driver.switch_to.frame(iframe)
                el = driver.find_element(By.CSS_SELECTOR, ".payout:first-child")
                raw = el.text.replace("x","").replace(",",".")
            except:
                continue

        try:
            val = float(raw)
        except:
            continue

        if val != LAST:
            now = datetime.now(TZ_BR)
            payload = {
                "multiplier": f"{val:.2f}",
                "time": now.strftime("%H:%M:%S"),
                "date": now.strftime("%Y-%m-%d"),
                "color": getColorClass(val)
            }
            firebase_queue.put((cfg["firebase_path"], payload, cfg["nome"]))
            LAST = val
            LAST_TIME = time()

        # Inatividade
        if time() - LAST_TIME > TEMPO_MAX_INATIVIDADE:
            STOP_EVENT.set()
            return

        # Reinício diário (23:59 - 00:05)
        if now.hour == 23 and now.minute >= 59 or now.hour == 0 and now.minute <= 5:
            STOP_EVENT.set()
            return

        sleep(POLLING_INTERVAL)

# =============================================================
# 🔄 SUPERVISOR
# =============================================================
def run():
    STOP_EVENT.clear()
    driver = None

    try:
        driver = initialize_driver()
        handles = setup_tabs(driver)

        threads = []
        for cfg in CONFIG_BOTS:
            t = threading.Thread(target=start_bot, args=(driver, cfg, handles[cfg["firebase_path"]]))
            t.start()
            threads.append(t)

        while not STOP_EVENT.is_set():
            sleep(1)

    finally:
        STOP_EVENT.set()
        for t in threads:
            t.join(timeout=2)
        if driver:
            driver.quit()
        sleep(5)

# =============================================================
# ▶️ MAIN
# =============================================================
if __name__ == "__main__":
    while True:
        try:
            run()
            print("♻️ Reiniciando...")
            sleep(5)
        except KeyboardInterrupt:
            break
