from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException

from time import sleep, time
from datetime import datetime, date
import threading
import firebase_admin
from firebase_admin import credentials, db
import os
import pytz
import logging

# =============================================================
# 🔥 GOATHBOT V6.1 - STABLE DUAL MODE (SQUARE CLOUD FIX)
# =============================================================

SERVICE_ACCOUNT_FILE = "serviceAccountKey.json"
DATABASE_URL = "https://history-dashboard-a70ee-default-rtdb.firebaseio.com"
URL_DO_SITE = "https://www.goathbet.com"

CONFIG_BOTS = [
    {
        "nome": "ORIGINAL",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator",
        "firebase_path": "history"
    },
    {
        "nome": "AVIATOR 2",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator-2",
        "firebase_path": "aviator2"
    }
]

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
TZ_BR = pytz.timezone("America/Sao_Paulo")

# ====== AJUSTES CRÍTICOS ======
POLLING_INTERVAL = 0.3
TEMPO_MAX_INATIVIDADE = 360

logging.getLogger("WDM").setLevel(logging.ERROR)
os.environ["WDM_LOG_LEVEL"] = "0"

# =============================================================
# 🔧 FIREBASE
# =============================================================
if not firebase_admin._apps:
    cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
    firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})

print("✅ Conexão Firebase estabelecida.")

# =============================================================
# 🛠️ CHROME DRIVER OTIMIZADO
# =============================================================
def start_driver():
    options = webdriver.ChromeOptions()

    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    # 🔥 FLAGS DE ESTABILIDADE
    options.add_argument("--single-process")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--memory-pressure-off")
    options.add_argument("--disable-software-rasterizer")

    options.page_load_strategy = "eager"
    options.add_argument("--log-level=3")
    options.add_argument("--silent")

    try:
        return webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
    except:
        return webdriver.Chrome(
            service=Service("/usr/bin/chromedriver"),
            options=options
        )

# =============================================================
# 🔐 LOGIN + NAVEGAÇÃO
# =============================================================
def login_and_open(driver, link):
    driver.get(URL_DO_SITE)
    sleep(2)

    try:
        WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Entrar')]"))
        ).click()
        sleep(1)

        driver.find_element(By.NAME, "email").send_keys(EMAIL)
        driver.find_element(By.NAME, "password").send_keys(PASSWORD)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        sleep(3)
    except:
        pass

    driver.get(link)
    sleep(5)

# =============================================================
# 🧩 IFRAME + HIST
# =============================================================
def load_game_elements(driver):
    driver.switch_to.default_content()

    iframe = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located(
            (By.XPATH, "//iframe[contains(@src,'spribe') or contains(@src,'aviator')]")
        )
    )

    driver.switch_to.frame(iframe)

    hist = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, ".payouts-block, app-stats-widget")
        )
    )

    return hist

# =============================================================
# 🎨 COLOR
# =============================================================
def get_color(value):
    if value < 2: return "blue-bg"
    if value < 10: return "purple-bg"
    return "magenta-bg"

# =============================================================
# 🤖 BOT INDIVIDUAL
# =============================================================
def run_bot(cfg):
    nome = cfg["nome"]
    link = cfg["link"]
    path = cfg["firebase_path"]

    relogin_date = date.today()

    while True:
        driver = None
        try:
            print(f"🔄 [{nome}] Iniciando driver...")
            driver = start_driver()
            login_and_open(driver, link)

            hist = load_game_elements(driver)
            print(f"🚀 [{nome}] MONITORANDO EM '{path}'")

            last_sent = None
            last_time = time()

            while True:
                now = datetime.now(TZ_BR)

                if now.hour == 0 and now.minute < 5 and now.date() != relogin_date:
                    relogin_date = now.date()
                    raise Exception("Reinicio diário")

                if time() - last_time > TEMPO_MAX_INATIVIDADE:
                    raise Exception("Inatividade")

                if not hist.is_displayed():
                    raise Exception("Elemento invisível")

                values = []
                try:
                    items = hist.find_elements(By.CSS_SELECTOR, ".payout, .bubble-multiplier")
                    for it in items:
                        txt = it.text.replace("x", "").strip()
                        if txt:
                            values.append(float(txt))
                except:
                    pass

                if values:
                    v = values[0]
                    if v != last_sent:
                        last_sent = v
                        last_time = time()

                        entry = {
                            "multiplier": f"{v:.2f}",
                            "time": now.strftime("%H:%M:%S"),
                            "date": now.strftime("%Y-%m-%d"),
                            "color": get_color(v)
                        }

                        key = now.strftime("%Y-%m-%d_%H-%M-%S-%f")
                        db.reference(f"{path}/{key}").set(entry)

                        print(f"🔥 [{nome}] {entry['multiplier']}x")

                sleep(POLLING_INTERVAL)

        except Exception as e:
            print(f"❌ [{nome}] {e}. Reiniciando em 5s...")
            try:
                if driver:
                    driver.quit()
            except:
                pass
            sleep(5)

# =============================================================
# 🚀 MAIN
# =============================================================
if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD.")
        exit()

    print("==============================================")
    print("   GOATHBOT V6.1 - STABLE DUAL MONITORING")
    print("==============================================")

    for cfg in CONFIG_BOTS:
        threading.Thread(target=run_bot, args=(cfg,), daemon=True).start()
        sleep(2)

    while True:
        sleep(60)
