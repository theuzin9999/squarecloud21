from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from time import sleep, time
from datetime import datetime, date
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
import firebase_admin
from firebase_admin import credentials, db
import os
import pytz
import logging

# =============================================================
# 🔥 CONFIGURAÇÃO (V5.2 - DEBUG RAIO-X)
# =============================================================
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"
LINK_AVIATOR = "https://www.goathbet.com/pt/casino/spribe/aviator"

logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
TZ_BR = pytz.timezone("America/Sao_Paulo")

POLLING_INTERVAL = 0.5 # Um pouco mais lento para dar tempo de carregar o DOM
TEMPO_MAX_INATIVIDADE = 360

# =============================================================
# 🔧 FIREBASE
# =============================================================
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
    print("✅ Firebase conectado.")
except Exception as e:
    print(f"❌ ERRO FIREBASE: {e}")

# =============================================================
# 🛠️ DRIVER
# =============================================================
def start_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless") 
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.page_load_strategy = 'normal' # Mudado para normal para garantir carregamento total
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--log-level=3")

    try:
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except:
        return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)

def safe_click(driver, by, value, timeout=5):
    try:
        element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        driver.execute_script("arguments[0].click();", element)
        return True
    except: return False

def check_blocking_modals(driver):
    try:
        xpaths = ["//button[contains(., 'Sim')]", "//button[@data-age-action='yes']", "//button[contains(., 'Aceitar')]"]
        for xp in xpaths: safe_click(driver, By.XPATH, xp, 1)
    except: pass

def process_login(driver):
    print("➡️ Login...")
    try: driver.get(URL_DO_SITE)
    except: pass
    sleep(2)
    check_blocking_modals(driver)

    if safe_click(driver, By.XPATH, "//button[contains(., 'Entrar')]", 5) or \
       safe_click(driver, By.CSS_SELECTOR, 'a[href*="login"]', 5):
        sleep(1)
        try:
            driver.find_element(By.NAME, "email").send_keys(EMAIL)
            driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 5)
            sleep(3)
        except: pass
    
    print("➡️ Abrindo Aviator...")
    driver.get(LINK_AVIATOR)
    sleep(5)
    check_blocking_modals(driver)
    return True

def initialize_game_elements(driver):
    POSSIVEIS_IFRAMES = ['//iframe[contains(@src, "spribe")]', '//iframe[contains(@src, "aviator")]']
    driver.switch_to.default_content()
    
    iframe = None
    for xpath in POSSIVEIS_IFRAMES:
        try:
            iframe = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, xpath)))
            driver.switch_to.frame(iframe)
            print(f"✅ Iframe OK: {xpath}")
            break
        except: 
            driver.switch_to.default_content()
            continue

    if not iframe: return None, None

    # Tenta achar container de historico
    selectors = [".payouts-block", ".rounds-history", "app-payouts-history", ".history-list"]
    hist = None
    
    for sel in selectors:
        try:
            hist = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
            print(f"✅ Histórico Container OK: {sel}")
            break
        except: continue

    if not hist:
        # Tenta fallback por XPATH se CSS falhar
        try:
            hist = driver.find_element(By.XPATH, "//div[contains(@class, 'history')]")
            print("✅ Histórico Container OK (Via XPath)")
        except: pass

    return iframe, hist

def getColorClass(value):
    m = float(value)
    if 1.0 <= m < 2.0: return "blue-bg"
    if 2.0 <= m < 10.0: return "purple-bg"
    if m >= 10.0: return "magenta-bg"
    return "default-bg"

# =============================================================
# 🤖 LOGICA DE DEBUG
# =============================================================
def run_bot_session(relogin_done_for):
    driver = start_driver()
    process_login(driver)
    
    iframe, hist = initialize_game_elements(driver)
    if not hist: 
        driver.quit()
        raise Exception("Histórico não encontrado")

    print("\n🕵️ MODO DEBUG ATIVADO - ANALISANDO HTML...\n")
    debug_done = False
    
    LAST_SENT = None
    ULTIMO_MULTIPLIER_TIME = time()

    while True:
        now_br = datetime.now(TZ_BR)
        if now_br.hour == 0 and now_br.minute <= 5 and (relogin_done_for != now_br.date()):
            driver.quit(); return now_br.date()

        if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
            driver.quit(); raise Exception("Inatividade")

        try:
            # === BLOCO DEBUG (RODA SÓ UMA VEZ) ===
            if not debug_done:
                print("--- [INICIO RAIO-X] ---")
                # Pega o HTML interno do container para vermos as classes
                html_content = driver.execute_script("return arguments[0].innerHTML;", hist)
                text_content = hist.text
                print(f"📝 TEXTO VISÍVEL: '{text_content}'")
                print(f"💻 HTML INTERNO (Primeiros 300 chars): {html_content[:300]}")
                print("--- [FIM RAIO-X] ---")
                debug_done = True
            # =====================================

            resultados = []
            
            # TENTATIVA 1: Pega qualquer texto que pareça número dentro do histórico
            # Isso ignora classes específicas e foca no conteúdo
            raw_text = hist.text.replace("\n", " ").replace("x", "")
            parts = raw_text.split()
            for p in parts:
                try:
                    val = float(p)
                    if val >= 1.0: resultados.append(val)
                except: pass

            # TENTATIVA 2: Se o texto direto falhar, tenta buscar divs internas
            if not resultados:
                # Busca genérica por qualquer div com texto
                items = hist.find_elements(By.CSS_SELECTOR, "div, span, app-bubble-multiplier")
                for it in items:
                    txt = it.text.strip().replace("x", "")
                    if txt:
                        try:
                            val = float(txt)
                            if val >= 1.0: resultados.append(val)
                        except: pass

            if resultados:
                # Remove duplicados
                seen = set()
                uniq = [x for x in resultados if not (x in seen or seen.add(x))]
                
                if uniq:
                    novo = uniq[0]
                    if novo != LAST_SENT:
                        ULTIMO_MULTIPLIER_TIME = time()
                        print(f"🔥 CAPTURADO: {novo:.2f}x") # Log simples
                        
                        entry = {
                            "multiplier": f"{novo:.2f}",
                            "time": now_br.strftime("%H:%M:%S"),
                            "color": getColorClass(novo),
                            "date": now_br.strftime("%Y-%m-%d")
                        }
                        key = now_br.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                        db.reference(f"history/{key}").set(entry)
                        LAST_SENT = novo

            sleep(1) # Polling mais lento para debug

        except (StaleElementReferenceException, TimeoutException):
            print("⚠️ Elemento mudou. Recarregando...")
            driver.switch_to.default_content()
            iframe, hist = initialize_game_elements(driver)
            debug_done = False # Refaz o debug se recarregar

if __name__ == "__main__":
    print("INICIANDO V5.2 DEBUG...")
    relogin_date = date.today()
    while True:
        try:
            nova = run_bot_session(relogin_date)
            if nova: relogin_date = nova
        except Exception as e:
            print(f"Erro: {e}")
            sleep(5)
