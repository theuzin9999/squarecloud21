import os
import sys
import pytz
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
# CONTROLE GLOBAL
# =============================================================
DRIVER_LOCK = threading.Lock() 
STOP_EVENT = threading.Event() 

# =============================================================
# CONFIGURAÇÃO FIREBASE
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
# VARIÁVEIS E FUNÇÕES AUXILIARES
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
        try: db.reference(path).set(data)
        except: pass 
    threading.Thread(target=_send, daemon=True).start()

# =============================================================
# DRIVER (CORRIGIDO SEM VERSION_MAIN)
# =============================================================
def initialize_driver_instance():
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
    try:
        # Removido version_main para detectar automaticamente a versão do servidor
        driver = uc.Chrome(options=options)
        stealth(driver, languages=["pt-BR", "pt"], vendor="Google Inc.", platform="Win32", fix_hairline=True)
        return driver
    except Exception as e:
        print(f"⚠️ Erro ao iniciar driver: {e}")
        return None

# =============================================================
# LÓGICA DO BOT (INDENTAÇÃO CORRIGIDA)
# =============================================================
def find_game_elements_safe(driver):
    try:
        iframe = driver.find_element(By.XPATH, '//iframe[contains(@src, "spribe")]')
        driver.switch_to.frame(iframe)
        hist = driver.find_element(By.CSS_SELECTOR, "app-stats-widget, .payouts-block")
        return iframe, hist
    except: return None, None

def start_bot(driver, game_handle, firebase_path):
    nome_log = "AVIATOR 1" if "history" in firebase_path else "AVIATOR 2"
    print(f"🚀 INICIADO: {nome_log}")
    
    LAST_SENT = None
    ULTIMO_MULTIPLIER_TIME = time()
    
    # O loop AGORA está dentro da função start_bot
    while not STOP_EVENT.is_set():
        raw_text = None
        with DRIVER_LOCK:
            try:
                driver.switch_to.window(game_handle)
                driver.switch_to.default_content()
                _, hist_element = find_game_elements_safe(driver)
                if hist_element:
                    raw_text = hist_element.find_element(By.CSS_SELECTOR, ".payout:first-child").text
            except: pass
        
        if raw_text:
            try:
                novo_valor = float(raw_text.replace('x', ''))
                if novo_valor != LAST_SENT:
                    now = datetime.now(TZ_BR)
                    payload = {"multiplier": f"{novo_valor:.2f}", "time": now.strftime("%H:%M:%S"), "color": getColorClass(novo_valor)}
                    enviar_firebase_async(f"{firebase_path}/{now.strftime('%Y%m%d_%H%M%S')}", payload)
                    LAST_SENT = novo_valor
                    ULTIMO_MULTIPLIER_TIME = time()
            except: pass
        
        if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
            STOP_EVENT.set()
        
        sleep(POLLING_INTERVAL)

# =============================================================
# SUPERVISOR
# =============================================================
def rodar_ciclo_monitoramento():
    STOP_EVENT.clear()
    DRIVER = initialize_driver_instance()
    if not DRIVER: return

    try:
        # [Seu código de login aqui...]
        t1 = threading.Thread(target=start_bot, args=(DRIVER, DRIVER.window_handles[0], FIREBASE_PATH_ORIGINAL), daemon=True)
        t1.start()
        
        while not STOP_EVENT.is_set(): sleep(2)
    finally:
        DRIVER.quit()
        gc.collect()

if __name__ == "__main__":
    while True:
        rodar_ciclo_monitoramento()
        sleep(5)
