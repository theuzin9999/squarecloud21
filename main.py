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

import undetected_chromedriver as uc
from selenium_stealth import stealth

import firebase_admin
from firebase_admin import credentials, db

# =============================================================
# ⚠️ CONTROLE GLOBAL DE THREADS E DRIVER
# =============================================================
DRIVER_LOCK = threading.Lock() 
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
# ⚙️ VARIÁVEIS OFICIAIS
# =============================================================
URL_DO_SITE = "https://go.goathbet.com/c/7vo"
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
    print("\n--- 🕵️ DIAGNÓSTICO DE CONEXÃO ---")
    try:
        ip = requests.get('https://api.ipify.org', timeout=10).text
        print(f"🌐 IP Público: {ip}")
    except Exception as e:
        print(f"⚠️ Alerta de Rede: {e}")

def limpar_pngs_antigos():
    arquivos_png = glob.glob("*.png")
    for f in arquivos_png:
        try: os.remove(f)
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
        except: pass 
    threading.Thread(target=_send, daemon=True).start()

def verificar_modais_bloqueio(driver):
    try:
        # Simplificado para evitar erros
        btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'ACEITAR') or contains(text(), 'Sim, sou')]")
        for btn in btns:
            driver.execute_script("arguments[0].click();", btn)
    except: pass

def stealth_script_inject(driver):
    stealth_js = "Object.defineProperty(navigator, 'webdriver', {get: () => false});"
    try:
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': stealth_js})
    except: pass

# =============================================================
# 🚀 DRIVER E LOGIN
# =============================================================
def initialize_driver_instance():
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    try:
        driver = uc.Chrome(options=options)
        stealth(driver, languages=["pt-BR", "pt"], vendor="Google Inc.", platform="Win32", fix_hairline=True)
        return driver
    except Exception as e:
        print(f"⚠️ Erro no driver: {e}")
        return None

def setup_tabs(driver):
    stealth_script_inject(driver)
    driver.get(URL_DO_SITE)
    sleep(10)
    # [Adicione aqui a lógica de preenchimento de login com try/except]
    return {FIREBASE_PATH_ORIGINAL: driver.current_window_handle, FIREBASE_PATH_2: None}

# =============================================================
# 🔄 LOOP DE CAPTURA (CORRIGIDO)
# =============================================================
def start_bot(driver, game_handle, firebase_path):
    nome_log = "AVIATOR 1" if "history" in firebase_path else "AVIATOR 2"
    print(f"🚀 INICIADO: {nome_log}")
    
    LAST_SENT = None
    ULTIMO_MULTIPLIER_TIME = time()
    estado_cookies = {'aceito': False}

    # INDENTAÇÃO CORRIGIDA ABAIXO
    while not STOP_EVENT.is_set():
        raw_text = None
        with DRIVER_LOCK:
            try:
                driver.switch_to.window(game_handle)
                # Lógica de coleta aqui...
                # Exemplo: raw_text = driver.find_element(...).text
            except Exception as e:
                print(f"Erro na thread {nome_log}: {e}")
        
        if raw_text:
            # Lógica de processamento e envio ao firebase
            pass
            
        if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
            STOP_EVENT.set()
        
        sleep(POLLING_INTERVAL)

# =============================================================
# 🚀 SUPERVISOR
# =============================================================
def rodar_ciclo_monitoramento():
    DRIVER = initialize_driver_instance()
    if not DRIVER: return
    
    try:
        handles = setup_tabs(DRIVER)
        # Iniciar threads...
        sleep(10)
    finally:
        DRIVER.quit()

if __name__ == "__main__":
    while True:
        rodar_ciclo_monitoramento()
        sleep(5)
