from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
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
# 🔥 GOATHBOT V7.4 - DUAL MONITORING (OTIMIZADO)
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

logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
TZ_BR = pytz.timezone("America/Sao_Paulo")

# AJUSTES DE PERFORMANCE
POLLING_INTERVAL = 0.5  # Aumentado para reduzir CPU (0.1 era muito agressivo)
TEMPO_MAX_INATIVIDADE = 360
MAX_EMPTY_PAYOUTS_COUNT = 60 # 30 segundos (60 * 0.5s)
TEMPO_VIDA_DRIVER = 2700 # 45 minutos em segundos (Reinicia para limpar RAM)

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
    """Inicia o driver isolado com otimização de RAM."""
    options = webdriver.ChromeOptions()
    
    # Flags críticas para rodar em container (SquareCloud) e economizar RAM
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-application-cache") # Desativa cache para economizar RAM
    options.add_argument("--window-size=1366,768") # Resolução menor economiza processamento
    options.page_load_strategy = 'eager'
    options.add_argument("--log-level=3")
    options.add_argument("--silent")
    
    # User-Agent fixo
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36")

    try:
        # Tenta instalar o driver adequado
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f"❌ [{nome_bot}] Erro ao criar driver: {e}")
        return None

def safe_click(driver, by, value, timeout=5):
    try:
        element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        try: element.click()
        except: driver.execute_script("arguments[0].click();", element)
        return True
    except: return False

def check_blocking_modals(driver):
    # Lista otimizada de modais
    xpaths = [
        "//button[contains(., 'Sim')]", 
        "//button[contains(., 'Aceitar')]",
        "//div[contains(@class, 'modal')]//button[contains(., 'Fechar')]"
    ]
    for xp in xpaths:
        try:
            # Tempo curto para não travar a thread
            if safe_click(driver, By.XPATH, xp, 1):
                sleep(0.5)
        except: pass

def process_login(driver, target_link):
    """Faz o login e navega para o jogo."""
    try: 
        driver.get(URL_DO_SITE)
        sleep(2)
    except: pass
    
    check_blocking_modals(driver)

    # Verifica se precisa logar
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
    """Busca apenas o Iframe e retorna-o."""
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
    
    relogin_date = date.today()

    while True: # Ciclo de Reinicialização do Driver
        driver = None
        start_time_driver = time() # Marca a hora que o driver iniciou

        try:
            print(f"\n🔄 [{nome}] Iniciando novo ciclo de driver...")
            driver = start_driver(nome)
            
            if driver is None:
                sleep(5)
                continue
            
            if not process_login(driver, link):
                raise Exception("Falha no login ou navegação")

            # 1. Inicializa Iframe
            iframe = initialize_game_elements(driver, nome)
            if iframe is None:
                raise Exception("Falha na inicialização do Iframe.")
            
            # 2. Aguarda carregamento visual
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

            # LOOP DE LEITURA (Ciclo Rápido)
            while True: 
                # 1. Checagem de Reinício Programado (Limpeza de RAM)
                uptime = time() - start_time_driver
                if uptime > TEMPO_VIDA_DRIVER:
                    print(f"♻️ [{nome}] Reinício preventivo de memória ({uptime/60:.0f} min).")
                    break # Sai do loop de leitura e reinicia o driver

                # 2. Checagem de Inatividade
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
                    
                    # Leitura dos dados
                    raw_text = payouts[0].get_attribute("innerText")
                    clean_text = raw_text.strip().lower().replace('x', '')

                    if not clean_text:
                        # Fallback
                        clean_text = payouts[0].get_attribute("data-value")

                    try:
                        novo = float(clean_text)
                    except:
                        sleep(POLLING_INTERVAL)
                        continue
                    
                    # Envio ao Firebase
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
                        
                        # Thread lock não é estritamente necessário para operações de rede simples,
                        # mas try/except é vital.
                        try:
                            db.reference(f"{path_fb}/{key}").set(entry)
                            print(f"🔥 [{nome}] {entry['multiplier']}x")
                            LAST_SENT = novo
                        except: pass

                    sleep(POLLING_INTERVAL)

                except (StaleElementReferenceException, NoSuchElementException):
                    # Tenta recuperar o iframe sem reiniciar tudo
                    iframe = initialize_game_elements(driver, nome)
                    if not iframe: break 
                except Exception:
                    break # Quebra para reiniciar o driver

        except Exception as e:
            print(f"❌ [{nome}] Erro: {e}. Reiniciando em 5s...")
        
        finally:
            # Limpeza robusta ao sair do ciclo do driver
            if driver:
                try: driver.quit()
                except: pass
            driver = None
            gc.collect() # Força coleta de lixo do Python
            sleep(5)

if __name__ == "__main__":
    # Limpeza Inicial Global (Apenas uma vez no boot)
    try:
        if os.name == 'nt': # Só roda no Windows
            subprocess.run("taskkill /f /im chromedriver.exe", shell=True, stderr=subprocess.DEVNULL)
            subprocess.run("taskkill /f /im chrome.exe", shell=True, stderr=subprocess.DEVNULL)
    except: pass

    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD.")
        sys.exit(1)
    
    print("==============================================")
    print(f"    GOATHBOT V7.4 - OTIMIZADO (RAM/CPU)")
    print(f"    Monitorando: {[b['nome'] for b in CONFIG_BOTS]}")
    print("==============================================")

    threads = []
    for config in CONFIG_BOTS:
        t = threading.Thread(target=run_single_bot, args=(config,))
        t.start()
        threads.append(t)
        # Delay importante entre o start das threads para não sobrecarregar CPU no boot
        sleep(10) 

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n🚫 Interrompido.")
