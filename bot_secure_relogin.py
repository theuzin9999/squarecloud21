from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
# REMOVIDO: from webdriver_manager.chrome import ChromeDriverManager (Não vamos usar para evitar conflito de versão)
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
import gc 

# =============================================================
# 🔥 GOATHBOT V7.5 - CORREÇÃO DE DRIVER SQUARE CLOUD
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

# AJUSTES DE PERFORMANCE
POLLING_INTERVAL = 0.5
TEMPO_MAX_INATIVIDADE = 360
MAX_EMPTY_PAYOUTS_COUNT = 60
TEMPO_VIDA_DRIVER = 2700 

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
# 🛠️ DRIVER E NAVEGAÇÃO (CORRIGIDO PARA SQUARE CLOUD)
# =============================================================
def start_driver(nome_bot):
    """Inicia o driver apontando para o binário do sistema."""
    options = webdriver.ChromeOptions()
    
    # ---------------------------------------------------------
    # 🔴 CONFIGURAÇÃO CRÍTICA PARA SQUARE CLOUD / LINUX
    # ---------------------------------------------------------
    # Aponta explicitamente para o Chromium instalado no container
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
        # Tenta usar o Selenium Manager nativo (sem ChromeDriverManager)
        # O Selenium 4.10+ detecta automaticamente o driver compatível com o binary_location
        return webdriver.Chrome(options=options)
    except Exception as e:
        print(f"❌ [{nome_bot}] Erro driver (Tentativa 1): {e}")
        # Fallback de segurança caso o path padrão falhe (tenta sem binary_location)
        try:
            options.binary_location = "" # Reseta path
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
            print("⚠️ Erro ou já logado.")
    
    driver.get(target_link)
    sleep(5) 
    check_blocking_modals(driver)
    return True

def initialize_game_elements(driver, nome_bot):
    try: driver.switch_to.default_content()
    except: pass
    
    try:
        print(f"[{nome_bot}] 🔎 Buscando Iframe...")
        iframe = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator") or contains(@src, "game-client")]'))
        )
        return iframe
    except TimeoutException:
        print(f"[{nome_bot}] ❌ Timeout: Iframe não encontrado.")
        return None 
    except Exception as e:
        print(f"[{nome_bot}] ❌ Erro ao focar Iframe: {e}")
        return None

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
        start_time_driver = time()

        try:
            print(f"\n🔄 [{nome}] Iniciando novo ciclo de driver...")
            driver = start_driver(nome)
            
            if driver is None:
                sleep(10)
                continue
            
            if not process_login(driver, link):
                raise Exception("Falha no login ou navegação")

            iframe = initialize_game_elements(driver, nome)
            if iframe is None:
                raise Exception("Falha na inicialização do Iframe.")
            
            try:
                driver.switch_to.default_content()
                driver.switch_to.frame(iframe) 
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block, app-stats-widget, .history-container"))
                )
                print(f"[{nome}] ✅ Jogo carregado e pronto.")
            except:
                raise Exception("Timeout esperando elementos do jogo.")

            LAST_SENT = None
            ULTIMO_MULTIPLIER_TIME = time()
            CONSECUTIVE_EMPTY_PAYOUTS = 0
            SELECTOR_MULTIPLIER = ".payouts-block .payout, .payout.ng-star-inserted, app-stats-widget .bubble-multiplier"

            while True: 
                uptime = time() - start_time_driver
                if uptime > TEMPO_VIDA_DRIVER:
                    print(f"♻️ [{nome}] Reinício preventivo de memória ({uptime/60:.0f} min).")
                    break 

                if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                    raise Exception("Inatividade detectada no jogo.")

                try:
                    driver.switch_to.default_content()
                    driver.switch_to.frame(iframe) 
                    
                    payouts = driver.find_elements(By.CSS_SELECTOR, SELECTOR_MULTIPLIER)
                    
                    if not payouts:
                        CONSECUTIVE_EMPTY_PAYOUTS += 1
                        if CONSECUTIVE_EMPTY_PAYOUTS > MAX_EMPTY_PAYOUTS_COUNT:
                             raise Exception("Falha ao ler histórico por tempo excessivo.")
                        sleep(POLLING_INTERVAL)
                        continue 
                    
                    CONSECUTIVE_EMPTY_PAYOUTS = 0
                    
                    raw_text = payouts[0].get_attribute("innerText")
                    clean_text = raw_text.strip().lower().replace('x', '')

                    if not clean_text:
                        clean_text = payouts[0].get_attribute("data-value")

                    try:
                        novo = float(clean_text)
                    except:
                        sleep(POLLING_INTERVAL)
                        continue
                    
                    if novo != LAST_SENT:
                        now_br = datetime.now(TZ_BR)
                        ULTIMO_MULTIPLIER_TIME = time()
                        
                        entry = {
                            "multiplier": f"{novo:.2f}",
                            "time": now_br.strftime("%H:%M:%S"),
                            "color": getColorClass(novo),
                            "date": now_br.strftime("%Y-%m-%d")
                        }
                        key = now_br.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                        
                        try:
                            db.reference(f"{path_fb}/{key}").set(entry)
                            print(f"🔥 [{nome}] {entry['multiplier']}x")
                            LAST_SENT = novo
                        except: pass

                    sleep(POLLING_INTERVAL)

                except (StaleElementReferenceException, NoSuchElementException):
                    iframe = initialize_game_elements(driver, nome)
                    if not iframe: break 
                except Exception:
                    break 

        except Exception as e:
            print(f"❌ [{nome}] Erro: {e}. Reiniciando em 5s...")
        
        finally:
            if driver:
                try: driver.quit()
                except: pass
            driver = None
            gc.collect() 
            sleep(5)

if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD.")
        sys.exit(1)
    
    print("==============================================")
    print(f"    GOATHBOT V7.5 - FIX SQUARE CLOUD")
    print("==============================================")

    threads = []
    for config in CONFIG_BOTS:
        t = threading.Thread(target=run_single_bot, args=(config,))
        t.start()
        threads.append(t)
        sleep(15) # Aumentei o delay para garantir que o Chrome 1 suba completamente antes do 2

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n🚫 Interrompido.")
