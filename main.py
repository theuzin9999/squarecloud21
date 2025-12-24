import os
import logging
import threading
import pytz
import gc
from time import sleep, time
from datetime import datetime, date
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
import firebase_admin
from firebase_admin import credentials, db

# =============================================================
# 🔥 GOATHBOT V6.7 - ULTRA RESILIENTE (FIX IFRAME CONTENT)
# =============================================================

# CONFIGURAÇÕES
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"
TZ_BR = pytz.timezone("America/Sao_Paulo")

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

CONFIG_BOTS = [
    {
        "nome": "AVIATOR_1",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator",
        "firebase_path": "history"
    },
    # 👇👇👇 (APAGUE AS ASPAS PARA ATIVAR AVIATOR 2)
    """
    {
        "nome": "AVIATOR_2",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator-2",
        "firebase_path": "aviator2"
    }
    """
]

logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

def init_firebase():
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
            firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
            print("✅ Firebase Conectado.")
        except Exception as e:
            print(f"❌ Erro Firebase: {e}")
            exit(1)

def start_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1366,768")
    chrome_options.add_argument("--mute-audio")
    chrome_options.binary_location = "/usr/bin/chromium"
    try:
        service = Service("/usr/bin/chromedriver")
        return webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"⚠️ Erro Driver: {e}")
        return None

def process_login(driver, target_link):
    print("🔑 Efetuando Login...")
    try:
        driver.get(URL_DO_SITE)
        sleep(3)
        # Login Simplificado
        driver.get("https://www.goathbet.com/pt/login")
        sleep(2)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "email"))).send_keys(EMAIL)
        driver.find_element(By.NAME, "password").send_keys(PASSWORD)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        sleep(5)
    except: pass
    print(f"🎮 Indo para o jogo: {target_link}")
    driver.get(target_link)
    sleep(5)

def get_game_elements(driver):
    try:
        driver.switch_to.default_content()
        # Busca o iframe
        iframes = ["//iframe[contains(@class, 'game-iframe')]", "//iframe[contains(@src, 'spribe')]"]
        found_iframe = None
        for path in iframes:
            try:
                found_iframe = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, path)))
                if found_iframe: break
            except: continue
        
        if not found_iframe: return None
        
        driver.switch_to.frame(found_iframe)
        
        # 🔥 AGUARDO AGRESSIVO PELO CONTEÚDO
        # Tenta achar o elemento que contém os números
        selectors = [".payouts-block", "app-stats-widget", ".payouts-wrapper", "app-stats-dropdown"]
        for sel in selectors:
            try:
                el = WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                if el: return el
            except: continue
            
        return None
    except: return None

def get_color_class(value):
    try:
        m = float(value)
        if m < 2.0: return "blue-bg"
        if m < 10.0: return "purple-bg"
        return "magenta-bg"
    except: return "default-bg"

def run_bot_thread(config):
    if isinstance(config, str): return
    nome, link, path_fb = config['nome'], config['link'], config['firebase_path']
    
    while True:
        driver = start_driver()
        try:
            process_login(driver, link)
            hist_element = get_game_elements(driver)
            
            if not hist_element:
                print(f"❌ [{nome}] Histórico não renderizou. Reiniciando...")
                driver.quit()
                continue

            print(f"✅ [{nome}] Monitorando...")
            last_sig = []
            timer = time()

            while True:
                if (time() - timer) > 180: break # Timeout 3min
                
                try:
                    # JavaScript para pegar os multiplicadores direto do DOM
                    raw_text = driver.execute_script("""
                        let el = document.querySelector('.payouts-block') || document.querySelector('app-stats-widget');
                        return el ? el.innerText : '';
                    """)
                    
                    if raw_text:
                        parts = raw_text.replace('x', '').replace('\n', ' ').split()
                        mults = []
                        for p in parts:
                            try:
                                val = float(p.replace(',', '.'))
                                if val >= 1.0: mults.append(val)
                            except: pass
                        
                        if mults and mults[:5] != last_sig:
                            timer = time()
                            last_sig = mults[:5]
                            newest = mults[0]
                            
                            now = datetime.now(TZ_BR)
                            key = now.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                            db.reference(f"{path_fb}/{key}").set({
                                "multiplier": f"{newest:.2f}",
                                "time": now.strftime("%H:%M:%S"),
                                "color": get_color_class(newest),
                                "date": now.strftime("%Y-%m-%d")
                            })
                            print(f"🔥 [{nome}] {newest:.2f}x")
                    
                    sleep(1)
                except:
                    hist_element = get_game_elements(driver)
                    if not hist_element: break
                    
        except Exception as e:
            print(f"⚠️ Erro: {e}")
        finally:
            if driver: driver.quit()
            sleep(10)

if __name__ == "__main__":
    init_firebase()
    active = [b for b in CONFIG_BOTS if isinstance(b, dict)]
    for cfg in active:
        threading.Thread(target=run_bot_thread, args=(cfg,)).start()
        sleep(30)
