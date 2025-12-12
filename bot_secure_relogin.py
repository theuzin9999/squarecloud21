from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from time import sleep, time
from datetime import datetime
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, NoSuchElementException
import firebase_admin
from firebase_admin import credentials, db
import os
import pytz
import logging
import threading
import sys
import subprocess
import traceback
import gc  # Importante para limpar memória RAM

# =============================================================
# ⚠️ CONTROLE GLOBAL DE THREADS E DRIVER
# =============================================================
DRIVER_LOCK = threading.Lock() 
STOP_EVENT = threading.Event() 

# =============================================================
# 🔥 GOATHBOT V6.2 - SUPER LIGHT (OTIMIZADO)
# =============================================================
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"

# CONFIGURAÇÃO DOS DOIS JOGOS
CONFIG_BOTS = [
    {
        "nome": "ORIGINAL",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator",
        "firebase_path": "history"
    },
    {
        "nome": "AVIATOR 2",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator-2",
        "firebase_path": "aviator2"
    }
]

# Configuração Limpa de Logs
logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
TZ_BR = pytz.timezone("America/Sao_Paulo")

# =============================================================
# ⚡ CONFIGURAÇÕES DE PERFORMANCE
# =============================================================
# Aumentado para 1.0s para reduzir drasticamente o uso de CPU.
# O jogo demora >5s entre rodadas, então 1s é seguro.
POLLING_INTERVAL = 1.0          
TEMPO_MAX_INATIVIDADE = 600     # 10 minutos sem novos dados
CICLO_MAXIMO_SEGUNDOS = 1800    # 30 minutos: Reinicia o navegador para limpar RAM acumulada

# =============================================================
# 🔧 FIREBASE
# =============================================================
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
    print("✅ Conexão Firebase estabelecida.")
except Exception as e:
    print(f"\n❌ ERRO CRÍTICO NO FIREBASE: {e}")
    sys.exit()

def getColorClass(value):
    try:
        m = float(value)
        if 1.0 <= m < 2.0: return "blue-bg"
        if 2.0 <= m < 10.0: return "purple-bg"
        if m >= 10.0: return "magenta-bg"
        return "default-bg"
    except: return "default-bg"

def enviar_firebase_async(path, data, nome_jogo):
    """Envia dados ao Firebase em uma thread separada"""
    def _send():
        try:
            key = datetime.now(TZ_BR).strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '')
            db.reference(f"{path}/{key}").set(data)
            print(f"🔥 [{nome_jogo.upper()}] {data['multiplier']}x às {data['time']}")
        except Exception:
            pass 
    threading.Thread(target=_send).start()

def verificar_modais_bloqueio(driver):
    """Fecha popups chatos"""
    xpaths = [
        "//button[contains(., 'Sim')]", 
        "//button[@data-age-action='yes']", 
        "//div[contains(text(), '18')]/following::button[1]",
        "//button[contains(., 'Aceitar')]",
        "//button[contains(., 'Fechar')]" 
    ]
    for xp in xpaths:
        try:
            btn = driver.find_element(By.XPATH, xp)
            if btn.is_displayed(): 
                driver.execute_script("arguments[0].click();", btn)
                sleep(0.5)
        except: pass

# =============================================================
# 🛠️ DRIVER E NAVEGAÇÃO (OTIMIZADO PARA RAM)
# =============================================================
def initialize_driver_instance():
    # 1. Limpeza de processos zumbis antes de começar
    try:
        if os.name == 'nt': # Windows
            subprocess.run("taskkill /f /im chromedriver.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            subprocess.run("taskkill /f /im chrome.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        else: # Linux (Square Cloud)
            os.system("pkill -9 chrome")
            os.system("pkill -9 chromedriver")
    except: pass

    options = webdriver.ChromeOptions()
    options.page_load_strategy = 'eager'
    options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage") # Vital para containers
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--window-size=1280,720") # Resolução menor gasta menos RAM
    options.add_argument("--disable-gpu") # Desativa GPU (economiza RAM em
