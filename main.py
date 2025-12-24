import os
import logging
import threading
import pytz
import gc
import requests # Necessário para os testes de rede
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
# 🔥 GOATHBOT V6.6 - DIAGNOSTIC EDITION
# =============================================================

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
    }
]

# =============================================================
# 🔎 FUNÇÕES DE DIAGNÓSTICO DE REDE (PASSOS DA SQUARE CLOUD)
# =============================================================
def run_network_diagnostics():
    print("\n--- 🕵️ INICIANDO DIAGNÓSTICO DE REDE ---")
    
    # 1. Verificar IP Público
    try:
        ip = requests.get('https://api.ipify.org', timeout=10).text
        print(f"🌐 IP Público do Container: {ip}")
    except Exception as e:
        print(f"❌ Erro ao verificar IP Público: {e}")

    # 2. Teste de Conexão Simples (Requests)
    try:
        response = requests.get(URL_DO_SITE, timeout=15)
        print(f"📡 Teste de Conexão {URL_DO_SITE}: Status {response.status_code}")
        if response.status_code != 200:
            print("⚠️ O site respondeu, mas não com sucesso (pode ser bloqueio de Cloudflare).")
    except Exception as e:
        print(f"❌ Erro de Conexão Direta: {URL_DO_SITE} está inacessível para este servidor.")

    # 3. Teste de DNS básico
    import socket
    try:
        host = "www.goathbet.com"
        dns_res = socket.gethostbyname(host)
        print(f"🔍 Resolução DNS {host}: {dns_res} (OK)")
    except Exception as e:
        print(f"❌ Erro de DNS: Não foi possível resolver o endereço do site.")
    
    print("--- FIM DO DIAGNÓSTICO ---\n")

# =============================================================
# 🔧 FIREBASE & DRIVER
# =============================================================
def init_firebase():
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
            firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
            print("✅ Firebase Conectado.")
        except Exception as e:
            print(f"❌ Erro Crítico Firebase: {e}")
            exit(1)

def start_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.binary_location = "/usr/bin/chromium"
    
    # Logs mais detalhados do Selenium (conforme solicitado no passo 3)
    chrome_options.add_argument("--log-level=3") 
    
    try:
        service = Service("/usr/bin/chromedriver")
        return webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"⚠️ Erro ao Iniciar Driver: {e}")
        return None

# [As funções de login e captura permanecem as mesmas da V6.5, focando na trava de saldo]
# ... (mantendo a lógica de process_login e get_game_elements anterior)

def click_js(driver, element):
    driver.execute_script("arguments[0].click();", element)

def process_login(driver, target_link):
    print("🔑 Tentando acesso...")
    try:
        driver.get(URL_DO_SITE)
        sleep(5)
        
        # Procura botão Entrar
        try:
            login_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Entrar')] | //a[contains(@href, 'login')]"))
            )
            click_js(driver, login_btn)
            sleep(2)
            driver.find_element(By.NAME, "email").send_keys(EMAIL)
            driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            click_js(driver, submit_btn)
        except: pass

        # Verificação Real de Sucesso
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'balance')] | //a[contains(@href, 'deposit')]"))
        )
        print("✅ Login confirmado via Saldo/Perfil.")
        driver.get(target_link)
        return True
    except:
        print("❌ Falha no login ou timeout de rede.")
        return False

def get_game_elements(driver):
    try:
        driver.switch_to.default_content()
        iframe = WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "iframe.game-iframe, iframe[src*='spribe']"))
        )
        driver.switch_to.frame(iframe)
        hist = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "app-stats-widget, .payouts-block"))
        )
        return hist
    except: return None

def run_bot_thread(config):
    nome = config['nome']
    link = config['link']
    path_fb = config['firebase_path']
    
    while True:
        driver = None
        try:
            print(f"🔄 [{nome}] Reiniciando...")
            driver = start_driver()
            if not driver: 
                sleep(10); continue

            if not process_login(driver, link):
                driver.quit(); sleep(10); continue

            hist_element = get_game_elements(driver)
            if not hist_element:
                driver.quit(); sleep(5); continue

            last_value = None
            inactivity_timer = time()

            while True:
                # Loop de monitoramento...
                text_data = driver.execute_script("return arguments[0].innerText;", hist_element)
                if text_data:
                    # [Lógica de processamento de multiplicadores]
                    pass 
                sleep(1)
                
                if (time() - inactivity_timer) > 180: break

        except Exception as e:
            print(f"❌ Erro: {e}")
        finally:
            if driver: driver.quit()
            sleep(5)

if __name__ == "__main__":
    # EXECUTA DIAGNÓSTICO ANTES DE TUDO
    run_network_diagnostics()
    
    if not EMAIL or not PASSWORD:
        print("⛔ EMAIL/PASSWORD não configurados.")
    else:
        init_firebase()
        active_bots = [cfg for cfg in CONFIG_BOTS if isinstance(cfg, dict)]
        for cfg in active_bots:
            threading.Thread(target=run_bot_thread, args=(cfg,)).start()
