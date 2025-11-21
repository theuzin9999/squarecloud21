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

logging.getLogger('selenium').setLevel(logging.WARNING)

# =============================================================
# FIREBASE
# =============================================================
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'

try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
    print("✅ Firebase Admin SDK inicializado com sucesso usando ARQUIVO.")
except Exception as e:
    print(f"❌ ERRO FIREBASE: {e}")
    exit()

# =============================================================
# CONFIG GERAL
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
# AUXILIARES
# =============================================================
def getColorClass(v):
    v = float(v)
    if 1.0 <= v < 2.0: return "blue-bg"
    if 2.0 <= v < 10.0: return "purple-bg"
    if v >= 10.0: return "magenta-bg"
    return "default-bg"

def safe_click(driver, by, value, timeout=4):
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        driver.execute_script("arguments[0].click();", el)
        return True
    except:
        return False

def safe_find(driver, by, value, timeout=4):
    try:
        return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))
    except:
        return None

def check_blocking_modals(driver):
    try:
        # Maior de 18
        for xp in [
            "//button[contains(., 'Sim')]",
            "//div[contains(text(), '18 anos')]/..//button[contains(., 'Sim')]",
            "//button[contains(@class, 'MuiButton') and contains(., 'Sim')]"
        ]:
            if safe_click(driver, By.XPATH, xp, 1):
                sleep(0.3)
                break

        # Cookies
        safe_click(driver, By.XPATH, "//button[contains(., 'Aceitar todos')]", 1)
        safe_click(driver, By.XPATH, "//button[contains(., 'Aceitar')]", 1)
    except:
        pass

# =============================================================
# DRIVER HEADLESS (ATUALIZADO)
# =============================================================
def start_driver():
    options = webdriver.ChromeOptions()
    options.page_load_strategy = 'eager'

    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--start-maximized")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--log-level=3")
    options.add_experimental_option('excludeSwitches', ['enable-logging'])

    service = Service("/usr/lib/chromium-browser/chromedriver")
    return webdriver.Chrome(service=service, options=options)

# =============================================================
# LOGIN COMPLETO (FUNCIONAL)
# =============================================================
def process_login(driver):

    print("➡️ Executando login automático...")

    driver.get(URL_DO_SITE)
    sleep(2)

    check_blocking_modals(driver)

    login_buttons = [
        (By.CSS_SELECTOR, 'button[data-testid="header-login-button"]'),
        (By.XPATH, "//button[contains(., 'Entrar')]"),
        (By.XPATH, "//button[contains(., 'Login')]"),
        (By.CSS_SELECTOR, "button[aria-label='Entrar']"),
        (By.CSS_SELECTOR, "button[class*='login']")
    ]

    abriu = False
    for by, sel in login_buttons:
        if safe_click(driver, by, sel, 3):
            abriu = True
            break

    if not abriu:
        print("❌ Botão 'Login' inicial não encontrado.")
        return False

    sleep(1)

    email_field = safe_find(driver, By.NAME, "email", 4)
    pass_field = safe_find(driver, By.NAME, "password", 4)

    if not email_field or not pass_field:
        print("❌ Campos de login não encontrados.")
        return False

    email_field.clear(); pass_field.clear()
    email_field.send_keys(EMAIL)
    pass_field.send_keys(PASSWORD)
    sleep(0.3)

    # Botão final
    submit_selectors = [
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.XPATH, "//button[contains(., 'Entrar')]"),
        (By.XPATH, "//button[contains(., 'Login')]")
    ]

    for by, sel in submit_selectors:
        if safe_click(driver, by, sel, 3):
            print("✅ Login enviado.")
            break

    sleep(4)
    check_blocking_modals(driver)

    print("ℹ️ Abrindo Aviator...")
    driver.get(LINK_AVIATOR)
    sleep(2)
    check_blocking_modals(driver)

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe")]'))
        )
    except:
        sleep(3)

    return True

# =============================================================
# IFRAME + HISTÓRICO (PRIORIDADE SPRIBE)
# =============================================================
def initialize_game_elements(driver):

    PRIOR_IFRAME = ['//iframe[contains(@src, "spribe")]']
    PRIOR_HIST = [('.payouts-block', By.CSS_SELECTOR)]

    IF_FALLBACK = [
        '//iframe[contains(@src, "salsagator")]',
        '//iframe[contains(@src, "/aviator/")]',
        '//iframe[contains(@src, "aviator")]',
        '//iframe[contains(@src, "game")]'
    ]

    HIST_FALLBACK = [
        ('div.payouts-block', By.CSS_SELECTOR),
        ('.rounds-history', By.CSS_SELECTOR),
        ('.history-list', By.CSS_SELECTOR),
        ('[data-testid="history"]', By.CSS_SELECTOR)
    ]

    driver.switch_to.default_content()
    iframe = None

    for xp in PRIOR_IFRAME:
        try:
            iframe = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xp)))
            driver.switch_to.frame(iframe)
            print(f"✅ Iframe encontrado com XPath: {xp}")
            break
        except:
            iframe = None

    if not iframe:
        for xp in IF_FALLBACK:
            try:
                iframe = WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.XPATH, xp)))
                driver.switch_to.frame(iframe)
                print(f"⚠️ Iframe alternativo encontrado: {xp}")
                break
            except:
                iframe = None

    if not iframe:
        print("❌ Nenhum iframe encontrado.")
        return None, None

    # histórico
    hist = None
    for selector, by in PRIOR_HIST:
        try:
            hist = WebDriverWait(driver, 3).until(EC.presence_of_element_located((by, selector)))
            print(f"✅ Seletor de histórico encontrado: {selector}")
            break
        except:
            hist = None

    if not hist:
        for selector, by in HIST_FALLBACK:
            try:
                hist = WebDriverWait(driver, 3).until(EC.presence_of_element_located((by, selector)))
                print(f"⚠️ Histórico alternativo encontrado: {selector}")
                break
            except:
                hist = None

    if not hist:
        print("❌ Nenhum seletor de histórico encontrado.")
        return None, None

    return iframe, hist

# =============================================================
# LOOP PRINCIPAL
# =============================================================
def run_bot_session(relogin_done_for):

    driver = None
    try:
        driver = start_driver()

        if not process_login(driver):
            raise Exception("Falha no login")

        iframe, hist = initialize_game_elements(driver)
        if not hist:
            raise Exception("Erro ao encontrar elementos do jogo")

        LAST_SENT = None
        ULTIMO_ENVIO = time()
        ULTIMO_MULTIPLIER_TIME = time()

        print("🚀 Captura TURBO iniciada.\n")

        while True:

            now_br = datetime.now(TZ_BR)

            if now_br.hour == 0 and now_br.minute <= 5 and relogin_done_for != now_br.date():
                print("🕛 Reinício diário.")
                driver.quit()
                return now_br.date()

            if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                raise Exception("Inatividade")

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
                        key = now_br.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')

                        entry = {
                            "multiplier": raw,
                            "time": now_br.strftime("%H:%M:%S"),
                            "color": getColorClass(novo),
                            "date": now_br.strftime("%Y-%m-%d")
                        }

                        db.reference(f"history/{key}").set(entry)
                        print(f"🔥 {raw}x salvo às {entry['time']}")

                        LAST_SENT = novo
                        ULTIMO_ENVIO = time()
                        ULTIMO_MULTIPLIER_TIME = time()

            except (StaleElementReferenceException, TimeoutException, WebDriverException):
                print("⚠️ Reconectando elementos...")
                driver.switch_to.default_content()
                check_blocking_modals(driver)
                iframe, hist = initialize_game_elements(driver)
                if not hist:
                    raise Exception("Reconexão falhou")

            sleep(POLLING_INTERVAL)

    except Exception as e:
        print(f"❌ Sessão encerrada: {e}")
        if driver:
            try: driver.quit()
            except: pass
        raise e


# =============================================================
# GUARDIÃO
# =============================================================
def run_guardian():
    print("\n==============================================")
    print("         INICIALIZANDO GOATHBOT")
    print("==============================================")

    relogin_date = date.today()

    while True:
        try:
            nova = run_bot_session(relogin_date)
            if nova:
                relogin_date = nova

        except KeyboardInterrupt:
            print("🛑 Bot finalizado.")
            break

        except Exception as e:
            print("🔄 Reiniciando em 5s...")
            sleep(5)

# =============================================================
# START
# =============================================================
if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD.")
    else:
        run_guardian()
