from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
# from webdriver_manager.chrome import ChromeDriverManager # Removido para SquareCloud
from time import sleep, time
from datetime import datetime, date
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException, NoSuchElementException
import firebase_admin
from firebase_admin import credentials, db
import os
import pytz
import logging
import threading
import sys
import subprocess
import gc # Garbage Collector

# =============================================================
# 🔥 GOATHBOT V7.7 - FIX LOOP DE CONTEXTO E 24H
# =============================================================
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"

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

# Configuração de Logs
logging.basicConfig(level=logging.ERROR)

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
TZ_BR = pytz.timezone("America/Sao_Paulo")

# =============================================================
# ⚙️ CONFIGURAÇÕES DE TEMPO
# =============================================================
POLLING_INTERVAL = 0.5        # Velocidade de leitura
TEMPO_MAX_INATIVIDADE = 360   # 6 minutos sem dados = Reinicia
MAX_CONSECUTIVE_ERRORS = 50   # Tolerância para falha de leitura (25s) antes de reconfigurar

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
    sys.exit(1)

# =============================================================
# 🛠️ DRIVER E NAVEGAÇÃO
# =============================================================
def start_driver(nome_bot):
    """Inicia o driver apontando para o binário do sistema (Square Cloud)."""
    options = webdriver.ChromeOptions()
    
    # Configuração específica para Square Cloud / Linux
    options.binary_location = "/usr/bin/chromium"
    
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-notifications")
    options.add_argument("--window-size=1366,768")
    options.page_load_strategy = 'eager'
    
    options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    try:
        # Usa o Selenium Manager nativo (sem ChromeDriverManager)
        return webdriver.Chrome(options=options)
    except Exception as e:
        print(f"❌ [{nome_bot}] Erro driver (Tentativa 1): {e}")
        try:
            # Fallback de segurança (sem path específico)
            options.binary_location = ""
            return webdriver.Chrome(options=options)
        except Exception as e2:
            print(f"❌ [{nome_bot}] FALHA TOTAL DRIVER: {e2}")
            return None

def safe_click(driver, by, value, timeout=5):
    try:
        element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        try: element.click()
        except: driver.execute_script("arguments[0].click();", element)
        return True
    except: return False

def check_blocking_modals(driver):
    xpaths = [
        "//button[contains(., 'Sim')]", 
        "//button[contains(., 'Aceitar')]",
        "//div[contains(@class, 'modal')]//button[contains(., 'Fechar')]"
    ]
    for xp in xpaths:
        try:
            if safe_click(driver, By.XPATH, xp, 1):
                sleep(0.5)
        except: pass

def process_login(driver, target_link):
    try: 
        driver.get(URL_DO_SITE)
        sleep(2)
    except: pass
    
    check_blocking_modals(driver)

    if safe_click(driver, By.XPATH, "//button[contains(., 'Entrar')]", 3) or \
       safe_click(driver, By.CSS_SELECTOR, 'a[href*="login"]', 3):
        sleep(1)
        try:
            driver.find_element(By.NAME, "email").send_keys(EMAIL)
            driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            if safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 5):
                sleep(3)
        except: 
            pass
    
    driver.get(target_link)
    sleep(5) 
    check_blocking_modals(driver)
    return True

# =============================================================
# 🛠️ NOVA FUNÇÃO: CONFIGURAÇÃO DE CONTEXTO DO JOGO (FIX)
# =============================================================
def setup_game_context(driver, nome_bot):
    """Busca o Iframe, entra no seu contexto e espera pelo elemento do histórico."""
    # 1. Volta para o contexto principal antes de buscar o iframe
    try: driver.switch_to.default_content()
    except: pass
    
    try:
        # 1. Busca Iframe
        print(f"[{nome_bot}] 🔎 Buscando Iframe...")
        iframe = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator") or contains(@src, "game-client")]'))
        )
        
        # 2. Entra no Iframe
        driver.switch_to.frame(iframe) 
        
        # 3. Espera o elemento do histórico dentro do Iframe
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block, app-stats-widget, .history-container, .payout"))
        )
        print(f"[{nome_bot}] ✅ Jogo sincronizado. Monitorando...")
        return True
        
    except TimeoutException:
        print(f"[{nome_bot}] ❌ Timeout: Falha ao carregar Iframe ou elementos internos.")
        return False
    except Exception as e:
        print(f"[{nome_bot}] ❌ Erro ao configurar contexto do jogo: {e}")
        return False

def getColorClass(value):
    try:
        m = float(value)
        if 1.0 <= m < 2.0: return "blue-bg"
        if 2.0 <= m < 10.0: return "purple-bg"
        if m >= 10.0: return "magenta-bg"
        return "default-bg"
    except: return "default-bg"

# =============================================================
# 🤖 LÓGICA DE SESSÃO INDIVIDUAL (THREAD)
# =============================================================
def run_single_bot(bot_config):
    nome = bot_config["nome"]
    link = bot_config["link"]
    path_fb = bot_config["firebase_path"]
    
    while True: # Ciclo de Reinicialização do Driver
        driver = None
        
        try:
            print(f"\n🔄 [{nome}] Iniciando novo ciclo de driver...")
            driver = start_driver(nome)
            
            if driver is None:
                sleep(10)
                continue
            
            if not process_login(driver, link):
                print(f"⚠️ [{nome}] Falha no login, tentando continuar...")

            # 1. Configuração Inicial do Contexto (Iframe e Elementos)
            if not setup_game_context(driver, nome):
                raise Exception("Falha na inicialização do contexto do jogo.")
            
            print(f"🚀 [{nome}] MONITORANDO EM '{path_fb}'")

            LAST_SENT = None
            ULTIMO_MULTIPLIER_TIME = time()
            erros_consecutivos = 0
            
            # Seletor universal (o mesmo que estava funcionando)
            SELECTOR_MULTIPLIER = ".payouts-block .payout, .payout.ng-star-inserted, app-stats-widget .bubble-multiplier"

            # LOOP DE LEITURA (24H)
            while True: 
                now = datetime.now(TZ_BR)

                # 1. Reinício Total Diário (23:59)
                if now.hour == 23 and now.minute == 59:
                    print(f"🌙 [{nome}] Reinício Diário Programado (23:59).")
                    raise Exception("Reinício Diário")

                # 2. Checagem de Inatividade (6 minutos)
                tempo_sem_dados = time() - ULTIMO_MULTIPLIER_TIME
                if tempo_sem_dados > TEMPO_MAX_INATIVIDADE:
                    raise Exception(f"Inatividade detectada ({tempo_sem_dados:.0f}s sem dados).")

                try:
                    # O driver JÁ DEVE ESTAR DENTRO DO IFRAME.
                    payouts = driver.find_elements(By.CSS_SELECTOR, SELECTOR_MULTIPLIER)
                    
                    if not payouts:
                        erros_consecutivos += 1
                        if erros_consecutivos > MAX_CONSECUTIVE_ERRORS:
                             # Falha prolongada: RE-CONFIGURA O CONTEXTO
                             print(f"⚠️ [{nome}] Falha de leitura prolongada. Tentando reconfigurar contexto...")
                             if not setup_game_context(driver, nome):
                                 # Se a reconfiguração falhar, reinicia o driver
                                 raise Exception(f"Falha ao reconfigurar contexto após {MAX_CONSECUTIVE_ERRORS * POLLING_INTERVAL:.1f}s.")
                             
                             erros_consecutivos = 0
                        
                        sleep(POLLING_INTERVAL)
                        continue 
                    
                    erros_consecutivos = 0
                    
                    raw_text = payouts[0].get_attribute("innerText")
                    clean_text = raw_text.strip().lower().replace('x', '')

                    if not clean_text:
                        # Tenta atributo alternativo
                        clean_text = payouts[0].get_attribute("data-value")

                    try:
                        novo = float(clean_text)
                    except:
                        sleep(POLLING_INTERVAL)
                        continue
                    
                    if novo != LAST_SENT:
                        ULTIMO_MULTIPLIER_TIME = time()
                        
                        entry = {
                            "multiplier": f"{novo:.2f}",
                            "time": now.strftime("%H:%M:%S"),
                            "color": getColorClass(novo),
                            "date": now.strftime("%Y-%m-%d")
                        }
                        key = now.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                        
                        try:
                            db.reference(f"{path_fb}/{key}").set(entry)
                            print(f"🔥 [{nome}] {entry['multiplier']}x")
                            LAST_SENT = novo
                        except: pass

                    sleep(POLLING_INTERVAL)

                except (StaleElementReferenceException, NoSuchElementException) as e:
                    # Elemento perdido: TENTA RE-CONFIGURAR CONTEXTO
                    print(f"⚠️ [{nome}] Elemento perdido ou Stale. Tentando reconfigurar contexto...")
                    if not setup_game_context(driver, nome):
                        raise Exception("Falha ao reconfigurar contexto após perda de elemento.")
                    # Continua o loop na próxima iteração
                    continue
                except Exception as e:
                    # Qualquer outro erro na leitura é ignorado e o loop tenta novamente
                    sleep(1)
                    continue

        except Exception as e:
            print(f"❌ [{nome}] Reiniciando Driver: {e}")
            if driver:
                try: driver.quit()
                except: pass
            driver = None
            gc.collect()
            sleep(10)

if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD.")
        sys.exit(1)
    
    print("==============================================")
    print(f"    GOATHBOT V7.7 - FIX CONTEXT LOOP")
    print("==============================================")

    threads = []
    for config in CONFIG_BOTS:
        t = threading.Thread(target=run_single_bot, args=(config,))
        t.start()
        threads.append(t)
        # Delay aumentado para dar tempo do Chrome 1 carregar antes do Chrome 2
        sleep(15) 

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n🚫 Interrompido.")
