import os
import logging
import threading
import pytz
import gc
import requests
from time import sleep, time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException, NoSuchElementException
import firebase_admin
from firebase_admin import credentials, db

# =============================================================
# 🔥 GOATHBOT V7.3 - ANTI-BLOCK + OTIMIZADO
# =============================================================

SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"
TZ_BR = pytz.timezone("America/Sao_Paulo")

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

CONFIG_BOTS = [
    {"nome": "AVIATOR_1", "link": "https://www.goathbet.com/pt/casino/spribe/aviator", "firebase_path": "history"},
    {"nome": "AVIATOR_2", "link": "https://www.goathbet.com/casino/spribe/aviator-vip", "firebase_path": "aviator2"}
]

def run_diagnostics():
    print("\n--- 🕵️ DIAGNÓSTICO DE CONEXÃO ---")
    try:
        ip = requests.get('https://api.ipify.org', timeout=10).text
        print(f"🌐 IP Público: {ip}")
        res = requests.get(URL_DO_SITE, timeout=10)
        print(f"📡 Status Site: {res.status_code}")
    except Exception as e:
        print(f"⚠️ Alerta de Rede: {e}")

def init_firebase():
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
            firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
            print("✅ Firebase Conectado.")
        except Exception as e:
            print(f"❌ Erro Crítico Firebase: {e}")

def start_driver():
    options = Options()
    options.page_load_strategy = 'eager'
    options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
    # Anti-Detecção
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    
    options.binary_location = "/usr/bin/chromium"
    
    try:
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)
        
        # Ocultar automação via JS
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
        return driver
    except Exception as e:
        print(f"⚠️ Erro ao Iniciar Driver: {e}")
        return None

def process_login(driver, target_link):
    try:
        driver.get(URL_DO_SITE)
        sleep(5)
        # Ocultar popups comuns
        driver.execute_script("document.querySelectorAll('button').forEach(b => { if(b.innerText.includes('Sim') || b.innerText.includes('Aceitar')) b.click() })")
        
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Entrar')]"))).click()
        sleep(2)
        driver.find_element(By.NAME, "email").send_keys(EMAIL)
        driver.find_element(By.NAME, "password").send_keys(PASSWORD)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        sleep(10)
        driver.get(target_link)
        sleep(8)
        return True
    except:
        return False

def get_game_elements(driver):
    try:
        driver.switch_to.default_content()
        iframe = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "iframe")))
        driver.switch_to.frame(iframe)
        return WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block")))
    except:
        return None

def run_bot_thread(config):
    nome = config['nome']
    while True:
        driver = start_driver()
        if not driver:
            sleep(30)
            continue
            
        if process_login(driver, config['link']):
            print(f"✅ [{nome}] Monitorando...")
            try:
                while True:
                    # Captura de dados simplificada
                    vals = driver.execute_script("return Array.from(document.querySelectorAll('.payout')).map(p => p.innerText)")
                    for raw in vals:
                        clean = raw.replace('x', '').strip()
                        if clean:
                            data = {"multiplier": clean, "time": datetime.now(TZ_BR).strftime("%H:%M:%S")}
                            db.reference(f"{config['firebase_path']}/{time()}").set(data)
                    sleep(2)
            except:
                pass
        
        driver.quit()
        gc.collect()
        sleep(10)

if __name__ == "__main__":
    run_diagnostics()
    init_firebase()
    for cfg in CONFIG_BOTS:
        threading.Thread(target=run_bot_thread, args=(cfg,), daemon=True).start()
        sleep(45)
    
    while True: sleep(60)
