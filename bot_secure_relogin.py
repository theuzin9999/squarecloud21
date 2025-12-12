from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
    NoSuchElementException,
)

from time import sleep, time
from datetime import datetime, date
import firebase_admin
from firebase_admin import credentials, db
import os
import pytz
import sys
import gc
import logging

# =============================================================
# 🔥 CONFIG
# =============================================================
SERVICE_ACCOUNT_FILE = "serviceAccountKey.json"
DATABASE_URL = "https://history-dashboard-a70ee-default-rtdb.firebaseio.com"
URL_DO_SITE = "https://www.goathbet.com"

CONFIG_BOTS = [
    {"nome": "ORIGINAL", "link": "https://www.goathbet.com/pt/casino/spribe/aviator", "firebase_path": "history"},
    {"nome": "AVIATOR 2", "link": "https://www.goathbet.com/pt/casino/spribe/aviator-2", "firebase_path": "aviator2"},
]

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

TZ_BR = pytz.timezone("America/Sao_Paulo")

# Ajustes pra SquareCloud
POLLING_INTERVAL = 0.08            # 0.05 é bem agressivo (CPU/RAM sobem). 0.08~0.15 costuma estabilizar.
TEMPO_MAX_INATIVIDADE = 360        # 6 min
MAX_EMPTY_COUNT = 250              # ~20s (250 * 0.08)
TAB_RELOAD_COOLDOWN = 12           # evita reload em loop
GC_EVERY_SEC = 300                 # gc.collect a cada 5 min

IFRAME_XPATH = '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'
HIST_SELECTOR = "app-stats-widget, .payouts-block"
PAYOUT_SELECTOR = ".payout:first-child, .bubble-multiplier:first-child"

# webdriver_manager log
logging.getLogger("WDM").setLevel(logging.ERROR)
os.environ["WDM_LOG_LEVEL"] = "0"


# =============================================================
# 🔥 FIREBASE
# =============================================================
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})
    print("✅ Conexão Firebase estabelecida.", flush=True)
except Exception as e:
    print(f"❌ ERRO CRÍTICO NO FIREBASE: {e}", flush=True)
    sys.exit(1)


# =============================================================
# 🧩 HELPERS
# =============================================================
def getColorClass(value):
    try:
        m = float(value)
        if 1.0 <= m < 2.0:
            return "blue-bg"
        if 2.0 <= m < 10.0:
            return "purple-bg"
        if m >= 10.0:
            return "magenta-bg"
        return "default-bg"
    except Exception:
        return "default-bg"


def safe_click(driver, by, value, timeout=5):
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        try:
            el.click()
        except Exception:
            driver.execute_script("arguments[0].click();", el)
        return True
    except Exception:
        return False


def check_blocking_modals(driver):
    xpaths = [
        "//button[contains(., 'Sim')]",
        "//button[@data-age-action='yes']",
        "//button[contains(., 'Aceitar')]",
        "//button[contains(., 'Fechar')]",
    ]
    for xp in xpaths:
        if safe_click(driver, By.XPATH, xp, 0.6):
            sleep(0.2)
            break


# =============================================================
# 🚀 DRIVER
# =============================================================
def start_driver():
    options = webdriver.ChromeOptions()
    options.page_load_strategy = "eager"
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")
    options.add_argument("--silent")

    # reduz consumo e instabilidade
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-sync")
    options.add_argument("--metrics-recording-only")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-features=Translate,BackForwardCache")

    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    try:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except Exception:
        return webdriver.Chrome(options=options)


def process_login(driver):
    driver.get(URL_DO_SITE)
    sleep(4)
    check_blocking_modals(driver)

    # tenta abrir modal de login se existir
    safe_click(driver, By.XPATH, "//button[contains(., 'Entrar')]", 2)
    sleep(1)

    try:
        email_el = driver.find_element(By.NAME, "email")
        pass_el = driver.find_element(By.NAME, "password")
        email_el.clear()
        pass_el.clear()
        email_el.send_keys(EMAIL)
        pass_el.send_keys(PASSWORD)
        safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 5)
        sleep(6)
    except Exception:
        # se já estiver logado, ok
        pass

    check_blocking_modals(driver)


# =============================================================
# 🎮 GAME ELEMENTS (A ESTRATÉGIA QUE FUNCIONA)
# =============================================================
def initialize_game_elements(driver):
    """
    Estratégia do seu bot local:
    - acha iframe
    - entra no iframe
    - acha o container de histórico (app-stats-widget ou payouts-block)
    - retorna (iframe, hist_element)
    """
    driver.switch_to.default_content()

    iframe = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.XPATH, IFRAME_XPATH))
    )
    driver.switch_to.frame(iframe)

    hist = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, HIST_SELECTOR))
    )
    return iframe, hist


def read_latest_multiplier(driver, state):
    """
    Lê sempre pelo hist_element cacheado:
    hist.find_element(.payout:first-child, .bubble-multiplier:first-child)
    """
    try:
        driver.switch_to.default_content()
        driver.switch_to.frame(state["iframe"])

        payout = state["hist"].find_element(By.CSS_SELECTOR, PAYOUT_SELECTOR)
        raw = payout.get_attribute("innerText") or ""
        raw = raw.strip().lower()
        if not raw:
            return None

        clean = raw.replace("x", "").strip()
        if not clean:
            return None
        return float(clean)

    except (StaleElementReferenceException, NoSuchElementException):
        state["iframe"] = None
        state["hist"] = None
        return None
    except Exception:
        return None


def push_firebase(firebase_path, now_br, mult):
    payload = {
        "multiplier": f"{mult:.2f}",
        "time": now_br.strftime("%H:%M:%S"),
        "color": getColorClass(mult),
        "date": now_br.strftime("%Y-%m-%d"),
    }
    key = now_br.strftime("%Y-%m-%d_%H-%M-%S-%f").replace(".", "-")
    db.reference(f"{firebase_path}/{key}").set(payload)
    return payload


# =============================================================
# 🧠 MAIN LOOP (1 DRIVER / 2 ABAS)
# =============================================================
def open_game_tab(driver, link):
    driver.execute_script("window.open('about:blank','_blank');")
    handle = driver.window_handles[-1]
    driver.switch_to.window(handle)
    driver.get(link)
    sleep(5)
    check_blocking_modals(driver)
    return handle


def ensure_game_ready(driver, state):
    """
    Garante que (iframe, hist) existam; se não, tenta reconstruir.
    """
    try:
        iframe, hist = initialize_game_elements(driver)
        state["iframe"] = iframe
        state["hist"] = hist
        state["empty_count"] = 0
        return True
    except Exception:
        state["iframe"] = None
        state["hist"] = None
        return False


def reload_game_tab(driver, state):
    """
    Recarrega só a aba do jogo (sem reiniciar driver).
    """
    now = time()
    if (now - state["last_reload"]) < TAB_RELOAD_COOLDOWN:
        return False

    state["last_reload"] = now
    driver.get(state["cfg"]["link"])
    sleep(5)
    check_blocking_modals(driver)
    return ensure_game_ready(driver, state)


def run_dual():
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD nas variáveis de ambiente.", flush=True)
        sys.exit(1)

    relogin_date = date.today()

    while True:
        driver = None
        try:
            print("\n🔄 Iniciando driver único (2 abas)...", flush=True)
            driver = start_driver()

            process_login(driver)
            base_handle = driver.current_window_handle

            states = {}

            # abre as duas abas e cacheia elementos (iframe + hist) por jogo
            for cfg in CONFIG_BOTS:
                handle = open_game_tab(driver, cfg["link"])
                st = {
                    "cfg": cfg,
                    "handle": handle,
                    "iframe": None,
                    "hist": None,
                    "last_sent": None,
                    "ultimo_multiplier_time": time(),
                    "empty_count": 0,
                    "last_reload": 0.0,
                }
                states[cfg["nome"]] = st
                ok = ensure_game_ready(driver, st)
                print(f"✅ [{cfg['nome']}] aba pronta: {ok}", flush=True)

            driver.switch_to.window(base_handle)
            print("🚀 MONITORANDO 2 JOGOS (alternando abas)", flush=True)

            last_gc = time()

            while True:
                now_br = datetime.now(TZ_BR)

                # reinício diário (madrugada)
                if now_br.hour == 0 and now_br.minute <= 5 and relogin_date != now_br.date():
                    relogin_date = now_br.date()
                    raise Exception("Reinício Diário")

                for nome, st in states.items():
                    # inatividade longa: pede reload da aba do jogo
                    if (time() - st["ultimo_multiplier_time"]) > TEMPO_MAX_INATIVIDADE:
                        driver.switch_to.window(st["handle"])
                        print(f"🚨 [{nome}] Sem dados há 6 min. Recarregando aba...", flush=True)
                        reload_game_tab(driver, st)
                        st["ultimo_multiplier_time"] = time()
                        continue

                    driver.switch_to.window(st["handle"])

                    # se perdeu iframe/hist, tenta recuperar (sem reset geral)
                    if st["iframe"] is None or st["hist"] is None:
                        ensure_game_ready(driver, st)

                    mult = read_latest_multiplier(driver, st)

                    if mult is None:
                        st["empty_count"] += 1
                        if st["empty_count"] > MAX_EMPTY_COUNT:
                            print(f"⚠️ [{nome}] Histórico não encontrado. Recarregando aba...", flush=True)
                            reload_game_tab(driver, st)
                            st["empty_count"] = 0
                        continue

                    st["empty_count"] = 0

                    if st["last_sent"] is None or mult != st["last_sent"]:
                        st["ultimo_multiplier_time"] = time()
                        try:
                            payload = push_firebase(st["cfg"]["firebase_path"], now_br, mult)
                            label = "AVIATOR 1" if nome == "ORIGINAL" else "AVIATOR 2"
                            print(f"🔥 [{label}] {payload['multiplier']}x", flush=True)
                        except Exception:
                            pass
                        st["last_sent"] = mult

                # gc periódico pra segurar RAM em runtime longo
                if (time() - last_gc) >= GC_EVERY_SEC:
                    gc.collect()
                    last_gc = time()

                sleep(POLLING_INTERVAL)

        except KeyboardInterrupt:
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass
            sys.exit(0)

        except Exception as e:
            print(f"❌ Falha: {e}. Reiniciando ciclo em 8s...", flush=True)
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass
            sleep(8)


if __name__ == "__main__":
    print("==============================================", flush=True)
    print("   GOATHBOT - DUAL AVIATOR (ESTRATÉGIA LOCAL)", flush=True)
    print("==============================================", flush=True)
    run_dual()
