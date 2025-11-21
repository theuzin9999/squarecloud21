from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from time import sleep, time
from datetime import datetime, date
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
import firebase_admin
from firebase_admin import credentials, db
import os
import pytz
import logging

# =============================================================
# 🔥 CONFIGURAÇÃO GERAL
# =============================================================
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"
LINK_AVIATOR = "https://www.goathbet.com/pt/casino/spribe/aviator"

# Limpeza de Logs
logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

# Credenciais
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
TZ_BR = pytz.timezone("America/Sao_Paulo")

# ⚡ CONFIGURAÇÕES TURBO
POLLING_INTERVAL = 0.1
TEMPO_MAX_INATIVIDADE = 360

# =============================================================
# 🔧 INICIALIZAÇÃO FIREBASE
# =============================================================
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
    print("✅ Firebase conectado.")
except Exception as e:
    print(f"❌ ERRO FIREBASE: {e}")

# =============================================================
# 🛠️ DRIVER E NAVEGAÇÃO
# =============================================================
def start_driver():
    options = webdriver.ChromeOptions()
    # Configurações para Rodar em Servidor (Square Cloud)
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless") 
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.page_load_strategy = 'eager'
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
    except:
        return False

def check_blocking_modals(driver):
    """Fecha modais chatos (+18 e Cookies)"""
    try:
        xpaths = [
            "//button[contains(., 'Sim')]", 
            "//button[@data-age-action='yes']",
            "//div[contains(text(), '18')]/following::button[1]"
        ]
        for xp in xpaths:
            if safe_click(driver, By.XPATH, xp, 1): break
        safe_click(driver, By.XPATH, "//button[contains(., 'Aceitar')]", 1)
    except: pass

def process_login(driver):
    print("➡️ Iniciando login (V5.1)...")
    try: driver.get(URL_DO_SITE)
    except: pass
    
    sleep(2)
    check_blocking_modals(driver)

    # --- CORREÇÃO: Busca genérica pelo botão "Entrar" ---
    login_aberto = False
    if safe_click(driver, By.XPATH, "//button[contains(., 'Entrar')]", 5): login_aberto = True
    elif safe_click(driver, By.CSS_SELECTOR, 'a[href*="login"]', 5): login_aberto = True

    if login_aberto:
        print("ℹ️ Modal aberto. Preenchendo...")
        sleep(1)
        try:
            # Tenta achar campos por name ou type
            try: driver.find_element(By.NAME, "email").send_keys(EMAIL)
            except: driver.find_element(By.CSS_SELECTOR, "input[type='email']").send_keys(EMAIL)
            
            try: driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            except: driver.find_element(By.CSS_SELECTOR, "input[type='password']").send_keys(PASSWORD)

            if safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 5):
                print("✅ Login enviado.")
                sleep(4)
        except:
            print("⚠️ Erro ao preencher campos (pode já estar logado).")
    
    print("➡️ Indo para Aviator...")
    driver.get(LINK_AVIATOR)
    
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe")]'))
        )
    except: pass
    
    check_blocking_modals(driver)
    return True

def initialize_game_elements(driver):
    # --- PRIORIDADE NO SPRIBE ---
    POSSIVEIS_IFRAMES = [
        '//iframe[contains(@src, "spribe")]',
        '//iframe[contains(@src, "/aviator/")]'
    ]
    
    driver.switch_to.default_content()
    iframe = None
    for xpath in POSSIVEIS_IFRAMES:
        try:
            iframe = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xpath)))
            driver.switch_to.frame(iframe)
            print(f"✅ Iframe SPRIBE conectado: {xpath}")
            break
        except: 
            driver.switch_to.default_content()
            continue

    if not iframe: return None, None

    try:
        hist = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block"))
        )
        print("✅ Histórico .payouts-block encontrado")
        return iframe, hist
    except:
        # Fallback
        try:
            hist = driver.find_element(By.CSS_SELECTOR, ".rounds-history")
            return iframe, hist
        except: return None, None

def getColorClass(value):
    m = float(value)
    if 1.0 <= m < 2.0: return "blue-bg"
    if 2.0 <= m < 10.0: return "purple-bg"
    if m >= 10.0: return "magenta-bg"
    return "default-bg"

# =============================================================
# 🤖 MOTOR DO BOT
# =============================================================
def run_bot_session(relogin_done_for):
    driver = None
    try:
        driver = start_driver()
        process_login(driver) 

        iframe, hist = initialize_game_elements(driver)
        if not hist: raise Exception("Elementos do jogo não carregaram")

        print("\n✅ GOATHBOT V5.1 RODANDO! (Novo código ativo)\n")
        
        LAST_SENT = None
        ULTIMO_MULTIPLIER_TIME = time()
        
        while True:
            # Reinício Diário
            now_br = datetime.now(TZ_BR)
            if now_br.hour == 0 and now_br.minute <= 5 and (relogin_done_for != now_br.date()):
                driver.quit()
                return now_br.date()

            # Inatividade
            if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                raise Exception("Inatividade excessiva")

            try:
                # Leitura
                resultados = []
                try:
                    items = hist.find_elements(By.CSS_SELECTOR, ".payouts-block .payout")
                    for it in items:
                        txt = it.text.strip().replace("x", "")
                        if txt: resultados.append(float(txt))
                except: pass

                if not resultados:
                     # Fallback texto
                    txt_full = hist.text.replace('x', '').replace('\n', ' ')
                    for val in txt_full.split():
                        try:
                            v = float(val)
                            if v >= 1.0: resultados.append(v)
                        except: pass

                # Envio
                if resultados:
                    # Remove duplicatas
                    seen = set()
                    uniq = [x for x in resultados if not (x in seen or seen.add(x))]
                    
                    if uniq:
                        novo = uniq[0]
                        if novo != LAST_SENT:
                            ULTIMO_MULTIPLIER_TIME = time()
                            raw = f"{novo:.2f}"
                            
                            entry = {
                                "multiplier": raw,
                                "time": now_br.strftime("%H:%M:%S"),
                                "color": getColorClass(novo),
                                "date": now_br.strftime("%Y-%m-%d")
                            }
                            key = now_br.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                            
                            try:
                                db.reference(f"history/{key}").set(entry)
                                print(f"🔥 {raw}x")
                                LAST_SENT = novo
                            except: pass
                
                sleep(POLLING_INTERVAL)

            except (StaleElementReferenceException, TimeoutException):
                driver.switch_to.default_content()
                check_blocking_modals(driver)
                iframe, hist = initialize_game_elements(driver)
                if not hist: raise Exception("Falha na reconexão")

    except Exception as e:
        print(f"❌ Sessão caiu: {e}. Reiniciando...")
        if driver:
            try: driver.quit()
            except: pass
        raise e

if __name__ == "__main__":
    print("==============================================")
    print("   GOATHBOT V5.1 (SERVIDOR ATUALIZADO)")
    print("==============================================")
    
    relogin_date = date.today()
    while True:
        try:
            nova = run_bot_session(relogin_date)
            if nova: relogin_date = nova
        except KeyboardInterrupt: break
        except: sleep(5)
