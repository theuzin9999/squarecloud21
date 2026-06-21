import os
import sys
import pytz
import logging
import threading
import gc
import requests
import subprocess
import traceback
import glob
from time import sleep, time
from datetime import datetime

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

# 🔥 BIBLIOTECA DE CAMUFLAGEM
import undetected_chromedriver as uc
from selenium_stealth import stealth

import firebase_admin
from firebase_admin import credentials, db

# =============================================================
# ⚠️ CONTROLE GLOBAL DE THREADS E DRIVER
# =============================================================
STOP_EVENT = threading.Event()

# =============================================================
# 🔥 CONFIGURAÇÃO FIREBASE
# =============================================================
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'

try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
    print("✅ Firebase Admin SDK inicializado.")
except Exception as e:
    print(f"\n❌ ERRO CONEXÃO FIREBASE: {e}")
    sys.exit()

# =============================================================
# ⚙️ VARIÁVEIS OFICIAIS GOATHBET
# =============================================================
URL_DO_SITE = "https://www.goathbet.bet"
LINK_AVIATOR_ORIGINAL = "https://www.goathbet.bet/casino/spribe/aviator"
LINK_AVIATOR_2 = "https://www.goathbet.bet/casino/spribe/aviator-vip"

FIREBASE_PATH_ORIGINAL = "history"
FIREBASE_PATH_2 = "aviator2"

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

POLLING_INTERVAL = 1.0
TEMPO_MAX_INATIVIDADE = 360
TZ_BR = pytz.timezone("America/Sao_Paulo")

# =============================================================
# 🔧 FUNÇÕES AUXILIARES
# =============================================================
def run_diagnostics():
    print("\n--- 🕵️ DIAGNÓSTICO ---")
    try:
        ip = requests.get('https://api.ipify.org', timeout=10).text
        print(f"🌐 IP: {ip}")
    except Exception as e:
        print(f"⚠️ Rede: {e}")

def limpar_pngs_antigos():
    try:
        arquivos_png = glob.glob("*.png")
        if arquivos_png:
            for f in arquivos_png:
                os.remove(f)
            print(f"🧹 Limpeza: {len(arquivos_png)} prints deletados.")
    except: pass

def getColorClass(value):
    try:
        m = float(value)
        if 1.0 <= m < 2.0: return "blue-bg"
        if 2.0 <= m < 10.0: return "purple-bg"
        if m >= 10.0: return "magenta-bg"
        return "default-bg"
    except: return "default-bg"

def enviar_firebase_async(path, data):
    def _send():
        try:
            db.reference(path).set(data)
            nome_jogo = path.split('/')[0].upper()
            if nome_jogo == "HISTORY": nome_jogo = "AVIATOR 1"
            print(f"🔥 {nome_jogo}: {data['multiplier']}x às {data['time']}")
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()

def create_driver():
    options = uc.ChromeOptions()
    options.page_load_strategy = 'eager'
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    
    driver = uc.Chrome(options=options, version_main=148)
    stealth(driver, languages=["pt-BR", "pt"], vendor="Google Inc.", platform="Win32")
    return driver

def process_login(driver, target_link):
    try:
        driver.get(URL_DO_SITE)
        sleep(8)
        
        try:
            btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'ACEITAR TODOS')]")))
            driver.execute_script("arguments[0].click();", btn)
        except: pass
        
        try:
            btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, "//span[contains(., 'Sim, sou maior de 18')]")))
            driver.execute_script("arguments[0].click();", btn)
        except: pass
        
        if WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Entrar')]"))):
            driver.execute_script("arguments[0].click();", driver.find_element(By.XPATH, "//button[contains(., 'Entrar')]"))
            sleep(3)
            driver.find_element(By.NAME, "email").send_keys(EMAIL)
            driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
            sleep(10)
    except Exception as e:
        print(f"❌ Login erro: {e}")
        return False
    
    driver.get(target_link)
    sleep(10)
    return True

def run_single_bot(nome, link, firebase_path):
    relogin_date = datetime.now(TZ_BR).date()
    
    while not STOP_EVENT.is_set():
        driver = None
        try:
            print(f"🔄 [{nome}] Iniciando driver...")
            driver = create_driver()
            
            if not process_login(driver, link):
                raise Exception("Login falhou")
            
            # Buscar iframe
            iframe = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'))
            )
            driver.switch_to.frame(iframe)
            
            hist = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block, app-stats-widget"))
            )
            print(f"🚀 [{nome}] MONITORANDO")
            
            LAST_SENT = None
            ULTIMO_MULTIPLIER_TIME = time()
            
            while True:
                now_br = datetime.now(TZ_BR)
                if now_br.hour == 0 and now_br.minute <= 5 and now_br.date() != relogin_date:
                    print(f"🌙 [{nome}] Reinício diário...")
                    break
                
                if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                    raise Exception("Inatividade")
                
                try:
                    first_payout = hist.find_element(By.CSS_SELECTOR, ".payout:first-child")
                    raw_text = first_payout.get_attribute("innerText")
                    clean_text = raw_text.strip().lower().replace('x', '')
                    
                    if clean_text:
                        novo = float(clean_text)
                        if novo != LAST_SENT:
                            payload = {
                                "multiplier": f"{novo:.2f}",
                                "time": now_br.strftime("%H:%M:%S"),
                                "color": getColorClass(novo),
                                "date": now_br.strftime("%Y-%m-%d")
                            }
                            key = now_br.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                            enviar_firebase_async(f"{firebase_path}/{key}", payload)
                            LAST_SENT = novo
                            ULTIMO_MULTIPLIER_TIME = time()
                except: pass
                
                sleep(POLLING_INTERVAL)
                
        except Exception as e:
            print(f"❌ [{nome}] Falha: {e}. Reiniciando em 5s...")
            if driver:
                try: driver.quit()
                except: pass
            sleep(5)

# =============================================================
# 🚀 EXECUTOR
# =============================================================
if __name__ == "__main__":
    run_diagnostics()
    limpar_pngs_antigos()
    
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD")
        sys.exit()
    
    print("==============================================")
    print("     BOT DUAL - GOATHBET AVIATOR       ")
    print("==============================================")
    
    t1 = threading.Thread(target=run_single_bot, args=("AVIATOR 1", LINK_AVIATOR_ORIGINAL, FIREBASE_PATH_ORIGINAL), daemon=True)
    t2 = threading.Thread(target=run_single_bot, args=("AVIATOR 2", LINK_AVIATOR_2, FIREBASE_PATH_2), daemon=True)
    
    t1.start()
    t2.start()
    
    while t1.is_alive() or t2.is_alive():
        if STOP_EVENT.is_set():
            break
        sleep(2)
