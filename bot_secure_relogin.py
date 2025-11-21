from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from time import sleep, time
from datetime import datetime, date
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException
)
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
import os
import pytz
import logging
from typing import Tuple, Optional

# Desabilita logs verbosos
logging.getLogger('selenium').setLevel(logging.WARNING)

# =============================================================
# 🔥 CONFIGURAÇÃO FIREBASE
# =============================================================
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'

try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {
            'databaseURL': DATABASE_URL
        })
    print("✅ Firebase inicializado com sucesso.")
except Exception as e:
    print(f"❌ ERRO FIREBASE: {e}")
    exit()

# =============================================================
# ⚙️ CONFIG GERAL
# =============================================================
URL_DO_SITE = "https://www.goathbet.com"
LINK_AVIATOR = "https://www.goathbet.com/pt/casino/spribe/aviator"

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

POLLING_INTERVAL = 0.1
INTERVALO_MINIMO_ENVIO = 0.1
TEMPO_MAX_INATIVIDADE = 360
TZ_BR = pytz.timezone("America/Sao_Paulo")

# =============================================================
# 🔧 FUNÇÕES AUXILIARES
# =============================================================
def getColorClass(value: float) -> str:
    if 1.0 <= value < 2.0:
        return "blue-bg"
    if 2.0 <= value < 10.0:
        return "purple-bg"
    if value >= 10.0:
        return "magenta-bg"
    return "default-bg"

def safe_click(driver: webdriver.Chrome, by: str, value: str, timeout: int = 5) -> bool:
    try:
        el = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((by, value))
        )
        driver.execute_script("arguments[0].click();", el)
        return True
    except:
        return False

def safe_find(driver: webdriver.Chrome, by: str, value: str, timeout: int = 5):
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
    except:
        return None

def check_blocking_modals(driver: webdriver.Chrome):
    try:
        safe_click(driver, By.XPATH, "//button[contains(., 'Sim')]", 1)
        safe_click(driver, By.XPATH, "//button[contains(., 'Aceitar')]", 1)
        safe_click(driver, By.XPATH, "//button[contains(., 'Aceitar todos')]", 1)
    except:
        pass

# =============================================================
# 🎯 BUSCA DE IFRAME E HISTÓRICO
# =============================================================
def initialize_game_elements(driver: webdriver.Chrome) -> Tuple[Optional[object], Optional[object]]:

    # PRIORIDADE ABSOLUTA
    IFRAME_PRIORITARIO = ['//iframe[contains(@src, "spribe")]']
    HIST_PRIORITARIO = [('.payouts-block', By.CSS_SELECTOR)]

    # FALLBACKS
    POSSIVEIS_IFRAMES = [
        '//iframe[contains(translate(@src,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"salsagator")]',
        '//iframe[contains(@src, "/aviator/")]',
        '//iframe[contains(@src, "aviator")]',
        '//iframe[contains(translate(@src,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"game")]'
    ]

    POSSIVEIS_HISTORICOS = [
        ('div.payouts-block', By.CSS_SELECTOR),
        ('.rounds-history', By.CSS_SELECTOR),
        ('.history-list', By.CSS_SELECTOR),
        ('[data-testid="history"]', By.CSS_SELECTOR)
    ]

    driver.switch_to.default_content()

    # === TENTA IFRAME PRINCIPAL ===
    for xpath in IFRAME_PRIORITARIO:
        try:
            iframe = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            driver.switch_to.frame(iframe)
            print(f"✅ Iframe encontrado com XPath: {xpath}")
            break
        except:
            iframe = None

    # === FALLBACK ===
    if not iframe:
        for xpath in POSSIVEIS_IFRAMES:
            try:
                iframe = WebDriverWait(driver, 4).until(
                    EC.presence_of_element_located((By.XPATH, xpath))
                )
                driver.switch_to.frame(iframe)
                print(f"⚠️ Iframe alternativo encontrado: {xpath}")
                break
            except:
                driver.switch_to.default_content()
                iframe = None

    if not iframe:
        print("❌ Nenhum iframe encontrado.")
        return None, None

    # === TENTA HISTÓRICO PRINCIPAL ===
    historico = None
    for selector, by_method in HIST_PRIORITARIO:
        try:
            historico = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((by_method, selector))
            )
            print(f"✅ Seletor de histórico encontrado: {selector}")
            break
        except:
            historico = None

    # === FALLBACK HISTÓRICO ===
    if not historico:
        for selector, by_method in POSSIVEIS_HISTORICOS:
            try:
                historico = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((by_method, selector))
                )
                print(f"⚠️ Histórico alternativo encontrado: {selector}")
                break
            except:
                historico = None

    if not historico:
        print("❌ Nenhum seletor de histórico encontrado.")
        return None, None

    return iframe, historico

# =============================================================
# 🔐 LOGIN AUTOMÁTICO
# =============================================================
def process_login(driver: webdriver.Chrome) -> bool:
    if not EMAIL or not PASSWORD:
        print("❌ EMAIL ou PASSWORD não configurados.")
        return False

    print("➡️ Login em andamento...")

    driver.get(URL_DO_SITE)
    sleep(2)
    check_blocking_modals(driver)

    # Abre modal de login
    safe_click(driver, By.CSS_SELECTOR, 'button[aria-label="Entrar"]', 4)
    sleep(1)

    email_input = safe_find(driver, By.NAME, "email", 3)
    pass_input = safe_find(driver, By.NAME, "password", 3)

    if email_input and pass_input:
        email_input.send_keys(EMAIL)
        pass_input.send_keys(PASSWORD)
        sleep(0.5)
        safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 4)

    sleep(4)
    check_blocking_modals(driver)

    driver.get(LINK_AVIATOR)
    sleep(3)
    check_blocking_modals(driver)

    return True

# =============================================================
# 🚀 DRIVER (HEADLESS)
# =============================================================
def start_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.page_load_strategy = 'eager'
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--headless")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")
    options.add_experimental_option('excludeSwitches', ['enable-logging'])

    service = Service("/usr/lib/chromium-browser/chromedriver")
    return webdriver.Chrome(service=service, options=options)

# =============================================================
# 🔄 LOOP PRINCIPAL
# =============================================================
def run_bot_session(relogin_done_for: date) -> Optional[date]:
    driver = None
    try:
        driver = start_driver()

        if not process_login(driver):
            raise Exception("Erro no login")

        iframe, hist = initialize_game_elements(driver)
        if not hist:
            raise Exception("Erro nos elementos do jogo")

        LAST_SENT = None
        ULTIMO_MULTIPLIER_TIME = time()
        ULTIMO_ENVIO = time()

        print("🚀 Captura TURBO iniciada.\n")

        while True:
            now_br = datetime.now(TZ_BR)

            if now_br.hour == 0 and now_br.minute <= 5 and relogin_done_for != now_br.date():
                print("🕛 Reinício programado.")
                driver.quit()
                return now_br.date()

            if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                print("🚨 Inatividade detectada.")
                raise Exception("Inatividade")

            # leitura
            try:
                driver.switch_to.frame(iframe)

                resultados = []
                items = hist.find_elements(By.CSS_SELECTOR, ".payouts-block .payout")

                if items:
                    for it in items:
                        txt = (it.text or "").strip().replace("x", "")
                        try:
                            v = float(txt)
                            if v >= 1.0:
                                resultados.append(v)
                        except:
                            pass
                else:
                    raw = hist.text.replace("x", "").replace("\n", " ")
                    for val in raw.split():
                        try:
                            v = float(val)
                            if v >= 1.0:
                                resultados.append(v)
                        except:
                            pass

                if resultados:
                    novo = resultados[0]
                    if novo != LAST_SENT and (time() - ULTIMO_ENVIO) > INTERVALO_MINIMO_ENVIO:

                        now_br = datetime.now(TZ_BR)
                        raw = f"{novo:.2f}"
                        entry_key = now_br.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')

                        entry = {
                            "multiplier": raw,
                            "time": now_br.strftime("%H:%M:%S"),
                            "color": getColorClass(novo),
                            "date": now_br.strftime("%Y-%m-%d")
                        }

                        db.reference(f"history/{entry_key}").set(entry)
                        print(f"🔥 {raw}x salvo às {entry['time']}")

                        LAST_SENT = novo
                        ULTIMO_ENVIO = time()
                        ULTIMO_MULTIPLIER_TIME = time()

            except (StaleElementReferenceException, TimeoutException, WebDriverException):
                print("⚠️ Reconectando iframe/histórico...")
                driver.switch_to.default_content()
                check_blocking_modals(driver)
                iframe, hist = initialize_game_elements(driver)
                if not hist:
                    raise Exception("Não reconectou")

            sleep(POLLING_INTERVAL)

    except Exception as e:
        print(f"❌ Erro na sessão: {e}")
        if driver:
            try:
                driver.quit()
            except:
                pass
        raise e

# =============================================================
# 🛡️ GUARDIÃO
# =============================================================
def run_guardian():
    print("\n==============================================")
    print("  GOATHBOT ONLINE V4.3 — PRIORIDADE SPRIBE")
    print("==============================================")
    
    relogin_date = date.today()

    while True:
        try:
            new_date = run_bot_session(relogin_date)
            if new_date:
                relogin_date = new_date

        except KeyboardInterrupt:
            print("🛑 Bot finalizado.")
            break
        except:
            print("🔄 Reiniciando em 5s...")
            sleep(5)

# =============================================================
# ▶️ INÍCIO
# =============================================================
if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD.")
    else:
        run_guardian()
