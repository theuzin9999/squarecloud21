import os
import logging
import threading
import pytz
import gc
import requests
import socket
from time import sleep, time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
import firebase_admin
from firebase_admin import credentials, db

# =============================================================
# 🔥 GOATHBOT V6.8 - FULL PERFORMANCE & DIAGNOSTIC
# =============================================================

# CONFIGURAÇÕES DE AMBIENTE
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"
TZ_BR = pytz.timezone("America/Sao_Paulo")

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

# CONFIGURAÇÃO DOS BOTS
CONFIG_BOTS = [
    {
        "nome": "AVIATOR_1",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator",
        "firebase_path": "history"
    },
    
    # ======================================================================
    # ⬇️ APAGUE AS ASPAS TRIPLAS (''' ACIMA E ABAIXO) PARA REATIVAR O BOT ⬇️
    # ======================================================================
    '''
    {
        "nome": "AVIATOR_2",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator-2",
        "firebase_path": "aviator2"
    }
    '''
    # ======================================================================
]

# Silenciar logs desnecessários
logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

# =============================================================
# 🔎 DIAGNÓSTICO INICIAL (REDE SQUARE CLOUD)
# =============================================================
def run_diagnostics():
    print("\n--- 🕵️ DIAGNÓSTICO DE CONEXÃO ---")
    try:
        ip = requests.get('https://api.ipify.org', timeout=10).text
        print(f"🌐 IP Público: {ip}")
        res = requests.get(URL_DO_SITE, timeout=10)
        print(f"📡 Status Site: {res.status_code}")
        dns = socket.gethostbyname("www.goathbet.com")
        print(f"🔍 DNS OK: {dns}")
    except Exception as e:
        print(f"⚠️ Alerta de Rede: {e}")
    print("----------------------------------\n")

# =============================================================
# 🔧 CONFIGURAÇÃO DO BROWSER (ANTI-DETECÇÃO)
# =============================================================
def start_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    chrome_options.binary_location = "/usr/bin/chromium"
    try:
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
        return driver
    except Exception as e:
        print(f"❌ Erro Driver: {e}")
        return None

def human_type(element, text):
    for char in text:
        element.send_keys(char)
        sleep(0.1)

# =============================================================
# 🔑 PROCESSO DE LOGIN ROBUSTO
# =============================================================
def process_login(driver, target_link):
    print("🔑 Iniciando Login...")
    try:
        driver.get(URL_DO_SITE)
        sleep(5)
        
        # Clica em Entrar
        try:
            btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Entrar')] | //a[contains(@href, 'login')]")))
            driver.execute_script("arguments[0].click();", btn)
            sleep(2)
        except:
            driver.get(f"{URL_DO_SITE}/pt/login")
            sleep(3)

        # Preenche dados
        u = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "email")))
        p = driver.find_element(By.NAME, "password")
        human_type(u, EMAIL)
        human_type(p, PASSWORD)
        
        submit = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        driver.execute_script("arguments[0].click();", submit)

        # Trava de Segurança: Espera o saldo/perfil aparecer
        print("⏳ Confirmando autenticação...")
        WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'balance')] | //a[contains(@href, 'deposit')]")))
        print("✅ Login confirmado.")
        
        driver.get(target_link)
        sleep(5)
        return True
    except:
        print("❌ Falha no login (Possível Captcha ou Seletor mudou).")
        return False

# =============================================================
# 🎮 CAPTURA DE DADOS (NOVOS SELETORES)
# =============================================================
def get_game_elements(driver):
    try:
        driver.switch_to.default_content()
        # Iframe novo + antigos
        iframe = WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.CSS_SELECTOR, "iframe.game-iframe, iframe[src*='spribe'], iframe[src*='launch.spribegaming']")))
        driver.switch_to.frame(iframe)
        
        # Seletores de histórico novos que você enviou
        hist = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block, app-stats-widget, .result-history, .payouts-wrapper")))
        return hist
    except:
        return None

def get_color_class(value):
    try:
        m = float(value)
        if 1.0 <= m < 2.0: return "blue-bg"
        if 2.0 <= m < 10.0: return "purple-bg"
        if m >= 10.0: return "magenta-bg"
    except: pass
    return "default-bg"

# =============================================================
# 🤖 LOOP PRINCIPAL
# =============================================================
def run_bot_thread(config):
    nome = config['nome']
    link = config['link']
    path_fb = config['firebase_path']
    
    while True:
        driver = None
        try:
            print(f"🔄 [{nome}] Iniciando...")
            driver = start_driver()
            if not driver or not process_login(driver, link):
                if driver: driver.quit()
                sleep(15); continue

            hist_el = get_game_elements(driver)
            if not hist_el:
                print(f"⚠️ [{nome}] Elementos não carregaram.")
                driver.quit(); sleep(10); continue

            print(f"✅ [{nome}] Monitorando...")
            last_val = None
            timer = time()

            while True:
                # Reset Diário
                if datetime.now(TZ_BR).strftime("%H:%M") == "23:59":
                    break

                if (time() - timer) > 200: break

                try:
                    raw = driver.execute_script("return arguments[0].innerText;", hist_el)
                    if raw:
                        vals = [v for v in raw.replace('x', '').split() if v.replace('.','').isdigit()]
                        if vals:
                            newest = vals[0]
                            if newest != last_val:
                                timer = time()
                                last_val = newest
                                now = datetime.now(TZ_BR)
                                data = {
                                    "multiplier": f"{float(newest):.2f}",
                                    "time": now.strftime("%H:%M:%S"),
                                    "color": get_color_class(newest),
                                    "date": now.strftime("%Y-%m-%d")
                                }
                                db.reference(f"{path_fb}/{now.strftime('%Y-%m-%d_%H-%M-%S')}").set(data)
                                print(f"🔥 [{nome}] {newest}x")
                    sleep(1.5)
                except:
                    break
        except Exception as e:
            print(f"❌ Erro Thread: {e}")
        finally:
            if driver: driver.quit()
            gc.collect(); sleep(5)

# =============================================================
# 🚀 START
# =============================================================
if __name__ == "__main__":
    run_diagnostics()
    if not EMAIL or not PASSWORD:
        print("⛔ Configure as variáveis de ambiente EMAIL e PASSWORD.")
    else:
        if not firebase_admin._apps:
            cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
            firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
        
        active_bots = [cfg for cfg in CONFIG_BOTS if isinstance(cfg, dict)]
        print(f"🚀 Iniciando {len(active_bots)} Bots...")
        
        for i, cfg in enumerate(active_bots):
            threading.Thread(target=run_bot_thread, args=(cfg,)).start()
            if i < len(active_bots)-1: sleep(40)
