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
import logging
import sys
import gc

# =============================================================
# 🔥 GOATHBOT V8 - DUAL AVIATOR (1 DRIVER / 2 ABAS) - ESTÁVEL
# =============================================================
SERVICE_ACCOUNT_FILE = "serviceAccountKey.json"
DATABASE_URL = "https://history-dashboard-a70ee-default-rtdb.firebaseio.com"
URL_DO_SITE = "https://www.goathbet.com"

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

# Logs do webdriver_manager
logging.getLogger("WDM").setLevel(logging.ERROR)
os.environ["WDM_LOG_LEVEL"] = "0"

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
TZ_BR = pytz.timezone("America/Sao_Paulo")

# Ajuste para reduzir CPU/RAM (0.1 é agressivo demais)
POLLING_INTERVAL = 0.20

TEMPO_MAX_INATIVIDADE = 360  # s
MAX_EMPTY_PAYOUTS_COUNT = 250  # ~50s (250 * 0.2)
TAB_RELOAD_COOLDOWN = 10  # s pra evitar reload em loop

# Seletor universal de histórico
SELECTOR_MULTIPLIER = (
    ".payouts-block .payout, "
    ".payout.ng-star-inserted, "
    "app-stats-widget .bubble-multiplier, "
    "[class*='payout-value'], "
    "[class*='multiplier-bubble']"
)

IFRAME_XPATH = (
    '//iframe[contains(@src, "spribe") or contains(@src, "aviator") or '
    'contains(@src, "game-client")]'
)

# =============================================================
# 🔧 FIREBASE
# =============================================================
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})
    print("✅ Conexão Firebase estabelecida.", flush=True)
except Exception as e:
    print(f"\n❌ ERRO CRÍTICO NO FIREBASE: {e}", flush=True)
    sys.exit(1)

# =============================================================
# 🛠️ DRIVER
# =============================================================
def start_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.page_load_strategy = "eager"
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--log-level=3")
    options.add_argument("--silent")
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


def safe_click(driver, by, value, timeout=5):
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((by, value))
        )
        try:
            element.click()
        except Exception:
            driver.execute_script("arguments[0].click();", element)
        return True
    except Exception:
        return False


def check_blocking_modals(driver):
    xpaths = [
        "//button[contains(., 'Sim')]",
        "//button[@data-age-action='yes']",
        "//div[contains(text(), '18')]/following::button[1]",
        "//button[contains(., 'Aceitar')]",
        "//div[contains(@class, 'modal')]//button[contains(., 'Fechar')]",
    ]
    for xp in xpaths:
        if safe_click(driver, By.XPATH, xp, 0.6):
            sleep(0.3)
            break


def process_login(driver):
    """Login 1 vez só."""
    driver.get(URL_DO_SITE)
    sleep(2)
    check_blocking_modals(driver)

    # Se já estiver logado, o formulário pode nem aparecer.
    clicked = (
        safe_click(driver, By.XPATH, "//button[contains(., 'Entrar')]", 3)
        or safe_click(driver, By.CSS_SELECTOR, 'a[href*="login"]', 3)
    )
    if clicked:
        sleep(1)
        try:
            email_el = driver.find_element(By.NAME, "email")
            pass_el = driver.find_element(By.NAME, "password")
            email_el.clear()
            pass_el.clear()
            email_el.send_keys(EMAIL)
            pass_el.send_keys(PASSWORD)
            if safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 5):
                sleep(3)
        except Exception:
            # pode ser que já esteja logado e o form não exista
            pass

    check_blocking_modals(driver)
    return True


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


# =============================================================
# 🎯 FUNÇÕES DE LEITURA POR ABA
# =============================================================
def open_game_in_tab(driver, link):
    """Abre link em nova aba e retorna handle."""
    driver.execute_script("window.open('about:blank', '_blank');")
    handle = driver.window_handles[-1]
    driver.switch_to.window(handle)
    driver.get(link)
    sleep(5)
    check_blocking_modals(driver)
    return handle


def find_iframe(driver):
    driver.switch_to.default_content()
    iframe = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.XPATH, IFRAME_XPATH))
    )
    return iframe


def ensure_iframe_and_ready(driver, state):
    """
    Garante que a aba atual está com iframe e histórico carregado.
    Atualiza state['iframe'].
    """
    try:
        iframe = find_iframe(driver)
        driver.switch_to.default_content()
        driver.switch_to.frame(iframe)

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".payouts-block, app-stats-widget, .history-container")
            )
        )
        state["iframe"] = iframe
        state["empty_count"] = 0
        return True
    except Exception:
        state["iframe"] = None
        return False


def read_latest_multiplier(driver, state):
    """
    Lê o multiplicador mais recente com o seletor universal.
    Retorna float ou None.
    """
    try:
        # foco no iframe atual
        driver.switch_to.default_content()
        if state.get("iframe") is None:
            return None

        driver.switch_to.frame(state["iframe"])
        payouts = driver.find_elements(By.CSS_SELECTOR, SELECTOR_MULTIPLIER)

        if not payouts:
            return None

        raw_text = (payouts[0].get_attribute("innerText") or "").strip().lower()
        clean = raw_text.replace("x", "").strip()

        if not clean:
            clean = (payouts[0].get_attribute("data-value") or "").strip()

        if not clean:
            return None

        try:
            return float(clean)
        except ValueError:
            return None

    except (StaleElementReferenceException, NoSuchElementException):
        # iframe/elemento morreu
        state["iframe"] = None
        return None
    except Exception:
        return None


def push_firebase(path_fb, now_br, multiplier):
    entry = {
        "multiplier": f"{multiplier:.2f}",
        "time": now_br.strftime("%H:%M:%S"),
        "color": getColorClass(multiplier),
        "date": now_br.strftime("%Y-%m-%d"),
    }
    key = now_br.strftime("%Y-%m-%d_%H-%M-%S-%f").replace(".", "-")
    db.reference(f"{path_fb}/{key}").set(entry)
    return entry


# =============================================================
# 🚀 LOOP PRINCIPAL (1 DRIVER / 2 ABAS)
# =============================================================
def run_dual():
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD.", flush=True)
        sys.exit(1)

    relogin_date = date.today()

    while True:
        driver = None
        try:
            print("\n🔄 Iniciando driver único (2 abas)...", flush=True)
            driver = start_driver()

            process_login(driver)

            # Aba 0: mantém site (ou uma aba base)
            base_handle = driver.current_window_handle

            # Abre as 2 abas de jogo
            states = {}
            for cfg in CONFIG_BOTS:
                handle = open_game_in_tab(driver, cfg["link"])
                states[cfg["nome"]] = {
                    "cfg": cfg,
                    "handle": handle,
                    "iframe": None,
                    "last_sent": None,
                    "ultimo_multiplier_time": time(),
                    "empty_count": 0,
                    "last_reload": 0.0,
                }
                ok = ensure_iframe_and_ready(driver, states[cfg["nome"]])
                print(
                    f"✅ [{cfg['nome']}] aba pronta: {ok}",
                    flush=True
                )
                sleep(1)

            # Volta para uma aba segura
            driver.switch_to.window(base_handle)

            print("🚀 MONITORANDO 2 JOGOS (alternando abas)", flush=True)

            while True:
                now_br = datetime.now(TZ_BR)

                # Reinício diário: 00:00 a 00:05
                if (
                    now_br.hour == 0
                    and now_br.minute <= 5
                    and (relogin_date != now_br.date())
                ):
                    print("🌙 Reinício diário.", flush=True)
                    relogin_date = now_br.date()
                    raise Exception("Reinício Diário")

                for nome, st in states.items():
                    cfg = st["cfg"]

                    # Inatividade por jogo
                    if (time() - st["ultimo_multiplier_time"]) > TEMPO_MAX_INATIVIDADE:
                        # tenta recarregar somente a aba desse jogo
                        if (time() - st["last_reload"]) > TAB_RELOAD_COOLDOWN:
                            print(f"⏳ [{nome}] Inatividade. Recarregando aba...", flush=True)
                            st["last_reload"] = time()
                            driver.switch_to.window(st["handle"])
                            driver.get(cfg["link"])
                            sleep(5)
                            check_blocking_modals(driver)
                            ensure_iframe_and_ready(driver, st)
                        continue

                    # troca para aba do jogo
                    driver.switch_to.window(st["handle"])

                    # garante iframe pronto
                    if st["iframe"] is None:
                        ensure_iframe_and_ready(driver, st)

                    mult = read_latest_multiplier(driver, st)

                    if mult is None:
                        st["empty_count"] += 1
                        if st["empty_count"] > MAX_EMPTY_PAYOUTS_COUNT:
                            # histórico sumiu por muito tempo: recarrega a aba (sem reiniciar driver)
                            if (time() - st["last_reload"]) > TAB_RELOAD_COOLDOWN:
                                print(
                                    f"⚠️ [{nome}] Histórico não encontrado por muito tempo. Recarregando aba...",
                                    flush=True,
                                )
                                st["last_reload"] = time()
                                driver.get(cfg["link"])
                                sleep(5)
                                check_blocking_modals(driver)
                                ensure_iframe_and_ready(driver, st)
                                st["empty_count"] = 0
                        continue
                    else:
                        st["empty_count"] = 0

                    # envia só se for novo
                    if st["last_sent"] is None or mult != st["last_sent"]:
                        st["ultimo_multiplier_time"] = time()
                        try:
                            entry = push_firebase(cfg["firebase_path"], now_br, mult)
                            print(f"🔥 [{nome}] {entry['multiplier']}x", flush=True)
                            st["last_sent"] = mult
                        except Exception:
                            # não explode o loop por falha pontual de firebase
                            pass

                    # micro-limpeza para segurar RAM em runtime longo
                    if int(time()) % 300 == 0:  # a cada ~5min
                        gc.collect()

                sleep(POLLING_INTERVAL)

        except KeyboardInterrupt:
            print("\n🚫 Interrompido.", flush=True)
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass
            sys.exit(0)

        except Exception as e:
            print(f"❌ Falha Crítica: {e}. Reiniciando em 10s...", flush=True)
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass
            sleep(10)


if __name__ == "__main__":
    print("==============================================", flush=True)
    print("    GOATHBOT V8 - DUAL AVIATOR (1 DRIVER)", flush=True)
    print("==============================================", flush=True)
    run_dual()
