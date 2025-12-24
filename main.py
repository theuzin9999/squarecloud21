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
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException, NoSuchElementException
import firebase_admin
from firebase_admin import credentials, db

# =============================================================
# 🔥 GOATHBOT V6.9 - UNIFIED STABLE EDITION
# =============================================================

# CONFIGURAÇÕES
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"
TZ_BR = pytz.timezone("America/Sao_Paulo")

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

# CONFIGURAÇÃO DOS BOTS (Mantendo apenas o Aviator 1 ativo conforme solicitado)
CONFIG_BOTS = [
    {
        "nome": "AVIATOR_1",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator",
        "firebase_path": "history"
    }
]

# Silenciar logs
logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

# =============================================================
# 🔎 DIAGNÓSTICO DE REDE
# =============================================================
def run_diagnostics():
    print("\n--- 🕵️ DIAGNÓSTICO DE CONEXÃO ---")
    try:
        ip = requests.get('https://api.ipify.org', timeout=10).text
        print(f"🌐 IP Público: {ip}")
        res = requests.get(URL_DO_SITE, timeout=10)
        print(f"📡 Status Site: {res.status_code}")
    except Exception as e:
        print(f"⚠️ Alerta de Rede: {e}")
    print("----------------------------------\n")

# =============================================================
# 🔧 DRIVER (Baseado na lógica estável do botaviator2)
# =============================================================
def start_driver():
    options = Options()
    options.page_load_strategy = 'eager' # Conforme botaviator2.py
    options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")
    # User-agent exato da versão que funciona
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
    
    # Caminho do Chromium no Square Cloud
    options.binary_location = "/usr/bin/chromium"
    
    try:
        service = Service("/usr/bin/chromedriver")
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f"❌ Erro ao iniciar navegador: {e}")
        return None

# =============================================================
# 🔑 LOGIN (Unificado com botaviator2)
# =============================================================
def process_login(driver, target_link):
    print("🔑 Iniciando Login...")
    try:
        driver.get(URL_DO_SITE)
        sleep(5)
        
        # Fecha modais de bloqueio (Lógica botaviator2)
        botoes_fechar = ["//button[contains(., 'Sim')]", "//button[contains(., 'Aceitar')]", "//button[contains(., 'Fechar')]"]
        for xpath in botoes_fechar:
            try:
                btn = driver.find_element(By.XPATH, xpath)
                if btn.is_displayed(): btn.click()
            except: pass

        # Clica em entrar
        try:
            btns = driver.find_elements(By.XPATH, "//button[contains(., 'Entrar')]")
            if btns: btns[0].click()
            sleep(2)
        except: pass
            
        # Preenchimento
        driver.find_element(By.NAME, "email").send_keys(EMAIL)
        driver.find_element(By.NAME, "password").send_keys(PASSWORD)
        sleep(1)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        print("✅ Dados enviados, aguardando 10s...")
        sleep(10) # Tempo de processamento do login

        print(f"🎮 Indo para: {target_link}")
        driver.get(target_link)
        sleep(5)
        return True
    except Exception as e:
        print(f"❌ Erro no processo de Login: {e}")
        return False

# =============================================================
# 🎮 CAPTURA DE DADOS
# =============================================================
def get_game_elements(driver):
    try:
        driver.switch_to.default_content()
        # Procura iframe via src ou classe
        iframe = WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'))
        )
        driver.switch_to.frame(iframe)
        # Elemento de histórico conforme botaviator2
        hist = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "app-stats-widget, .payouts-block"))
        )
        return hist
    except:
        return None

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
                print(f"⚠️ [{nome}] Jogo não carregou (Iframe não achado).")
                driver.quit(); sleep(10); continue

            print(f"✅ [{nome}] Monitorando...")
            last_val = None
            timer = time()

            while True:
                # Reinício diário
                if datetime.now(TZ_BR).strftime("%H:%M") == "23:59":
                    break

                # Timeout de inatividade (6 min conforme botaviator2)
                if (time() - timer) > 360: 
                    print(f"🚨 [{nome}] Inatividade detectada.")
                    break

                try:
                    # Leitura do primeiro valor do histórico
                    first_payout = hist_el.find_element(By.CSS_SELECTOR, ".payout:first-child, .bubble-multiplier:first-child")
                    raw = first_payout.get_attribute("innerText")
                    
                    if raw:
                        clean = raw.strip().lower().replace('x', '')
                        if clean:
                            newest = f"{float(clean):.2f}"
                            if newest != last_val:
                                timer = time()
                                last_val = newest
                                now = datetime.now(TZ_BR)
                                data = {
                                    "multiplier": newest,
                                    "time": now.strftime("%H:%M:%S"),
                                    "color": "blue-bg" if float(newest) < 2.0 else "purple-bg", # Simplificado para performance
                                    "date": now.strftime("%Y-%m-%d")
                                }
                                db.reference(f"{path_fb}/{now.strftime('%Y-%m-%d_%H-%M-%S')}").set(data)
                                print(f"🔥 [{nome}] {newest}x")
                    sleep(1)
                except (StaleElementReferenceException, NoSuchElementException):
                    # Se perder o elemento, tenta remapear antes de reiniciar o driver
                    hist_el = get_game_elements(driver)
                    if not hist_el: break
                except: break
        except Exception as e:
            print(f"❌ Erro Crítico: {e}")
        finally:
            if driver: driver.quit()
            gc.collect(); sleep(5)

# =============================================================
# 🚀 EXECUÇÃO
# =============================================================
if __name__ == "__main__":
    run_diagnostics()
    if not EMAIL or not PASSWORD:
        print("⛔ EMAIL e PASSWORD não configurados!")
    else:
        if not firebase_admin._apps:
            cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
            firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
        
        for cfg in CONFIG_BOTS:
            threading.Thread(target=run_bot_thread, args=(cfg,)).start()
