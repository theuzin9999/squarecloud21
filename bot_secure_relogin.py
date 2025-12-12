from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
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
# 🔥 GOATHBOT V7.6 - 24H & CORREÇÃO DE LOOP
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

# Logs apenas de erros críticos
logging.basicConfig(level=logging.ERROR)

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
TZ_BR = pytz.timezone("America/Sao_Paulo")

# =============================================================
# ⚙️ CONFIGURAÇÕES DE TEMPO
# =============================================================
POLLING_INTERVAL = 0.5        # Velocidade de leitura
TEMPO_MAX_INATIVIDADE = 360   # 6 minutos sem dados = Reinicia
MAX_CONSECUTIVE_ERRORS = 50   # Tolerância para erros de leitura antes de reiniciar

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
        return webdriver.Chrome(options=options)
    except Exception as e:
        print(f"❌ [{nome_bot}] Erro driver: {e}")
        try:
            # Fallback sem binary location se falhar
            options.binary_location = ""
            return webdriver.Chrome(options=options)
        except:
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
            pass # Assume que pode já estar logado
    
    driver.get(target_link)
    sleep(5) 
    check_blocking_modals(driver)
    return True

def initialize_game_elements(driver, nome_bot):
    try: driver.switch_to.default_content()
    except: pass
    
    try:
        print(f"[{nome_bot}] 🔎 Buscando Iframe...")
        # Aumentei o timeout para 30s para garantir
        iframe = WebDriverWait(driver, 30).until(
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
        
        try:
            print(f"\n🔄 [{nome}] Iniciando novo ciclo de driver...")
            driver = start_driver(nome)
            
            if driver is None:
                sleep(10)
                continue
            
            if not process_login(driver, link):
                print(f"⚠️ [{nome}] Falha no login, tentando continuar...")

            iframe = initialize_game_elements(driver, nome)
            if iframe is None:
                raise Exception("Falha na inicialização do Iframe.")
            
            # Espera carregar o jogo visualmente
            try:
                driver.switch_to.default_content()
                driver.switch_to.frame(iframe) 
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block, app-stats-widget, .history-container, .payout"))
                )
                print(f"[{nome}] ✅ Jogo sincronizado. Monitorando...")
            except:
                print(f"⚠️ [{nome}] Aviso: Elementos demoraram, mas tentando ler mesmo assim.")

            LAST_SENT = None
            ULTIMO_MULTIPLIER_TIME = time()
            erros_consecutivos = 0
            
            SELECTOR_MULTIPLIER = ".payouts-block .payout, .payout.ng-star-inserted, app-stats-widget .bubble-multiplier"

            # ==========================================
            # LOOP DE LEITURA (SEM TEMPO LIMITE DE VIDA)
            # ==========================================
            while True: 
                now = datetime.now(TZ_BR)

                # 1. Reinício Total Diário às 23:59
                if now.hour == 23 and now.minute == 59:
                    print(f"🌙 [{nome}] Reinício Diário Programado (23:59).")
                    raise Exception("Reinício Diário")

                # 2. Checagem de Inatividade (6 minutos)
                tempo_sem_dados = time() - ULTIMO_MULTIPLIER_TIME
                if tempo_sem_dados > TEMPO_MAX_INATIVIDADE:
                    raise Exception(f"Inatividade detectada ({tempo_sem_dados:.0f}s sem dados).")

                try:
                    driver.switch_to.default_content()
                    driver.switch_to.frame(iframe) 
                    
                    payouts = driver.find_elements(By.CSS_SELECTOR, SELECTOR_MULTIPLIER)
                    
                    if not payouts:
                        # Se não achou, conta erro mas não reinicia imediatamente
                        erros_consecutivos += 1
                        if erros_consecutivos > MAX_CONSECUTIVE_ERRORS:
                             print(f"⚠️ [{nome}] Falha de leitura prolongada.")
                             # Tenta buscar iframe de novo antes de reiniciar tudo
                             iframe = initialize_game_elements(driver, nome)
                             erros_consecutivos = 0 # Reseta se achar iframe
                        sleep(POLLING_INTERVAL)
                        continue 
                    
                    # Se achou, zera erros
                    erros_consecutivos = 0
                    
                    raw_text = payouts[0].get_attribute("innerText")
                    clean_text = raw_text.strip().lower().replace('x', '')

                    # Tenta atributo alternativo
                    if not clean_text:
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

                except (StaleElementReferenceException, NoSuchElementException):
                    # Elemento ficou velho? Tenta pegar o iframe de novo sem reiniciar o driver
                    iframe = initialize_game_elements(driver, nome)
                except Exception as e:
                    # Erro genérico na leitura: APENAS PRINTA, NÃO REINICIA O DRIVER
                    # Isso evita o loop de reinicialização por erros bobos
                    # print(f"⚠️ [{nome}] Erro leitura: {e}") 
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
    print(f"    GOATHBOT V7.6 - 24H FIXED")
    print("==============================================")

    threads = []
    for config in CONFIG_BOTS:
        t = threading.Thread(target=run_single_bot, args=(config,))
        t.start()
        threads.append(t)
        sleep(15) 

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n🚫 Interrompido.")
