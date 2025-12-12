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

# =============================================================
# 🔥 GOATHBOT V6.8 - DUAL MONITORING (SELECTORS REFORÇADOS)
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

POLLING_INTERVAL = 0.1 
TEMPO_MAX_INATIVIDADE = 360      

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
    """Inicia o driver isolado."""
    try:
        subprocess.run("taskkill /f /im chromedriver.exe", shell=True, check=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    except: pass 

    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.page_load_strategy = 'eager'
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--log-level=3")
    options.add_argument("--silent")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36")

    try:
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except:
        try:
             return webdriver.Chrome(options=options)
        except Exception as e:
            print(f"❌ [{nome_bot}] Erro driver: {e}")
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
        "//button[@data-age-action='yes']", 
        "//div[contains(text(), '18')]/following::button[1]",
        "//button[contains(., 'Aceitar')]",
        "//div[contains(@class, 'modal')]//button[contains(., 'Fechar')]"
    ]
    for xp in xpaths:
        if safe_click(driver, By.XPATH, xp, 0.5):
            sleep(0.5)
            break

def process_login(driver, target_link):
    """Faz o login e navega para o jogo."""
    try: driver.get(URL_DO_SITE)
    except: pass
    sleep(2)
    check_blocking_modals(driver)

    if safe_click(driver, By.XPATH, "//button[contains(., 'Entrar')]", 5) or \
       safe_click(driver, By.CSS_SELECTOR, 'a[href*="login"]', 5):
        sleep(1)
        try:
            driver.find_element(By.NAME, "email").send_keys(EMAIL)
            driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            
            if safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 5):
                sleep(3)
        except: 
            return False 
    
    driver.get(target_link)
    sleep(5) 
    check_blocking_modals(driver)
    return True

def initialize_game_elements(driver, nome_bot):
    """Busca apenas o Iframe e retorna-o."""
    try:
        driver.switch_to.default_content()
    except: pass
    
    iframe = None
    try:
        print(f"[{nome_bot}] 🔎 Buscando Iframe...")
        # Aumentei a espera para 20s
        iframe = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'))
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

    while True: # Loop Driver
        driver = None
        try:
            print(f"\n🔄 [{nome}] Iniciando novo ciclo de driver...")
            driver = start_driver(nome)
            
            if driver is None:
                raise Exception("start_driver falhou.")
            
            if not process_login(driver, link):
                raise Exception("Falha no login ou navegação")

            # 1. Inicializa Iframe
            iframe = initialize_game_elements(driver, nome)
            if iframe is None:
                raise Exception("Falha na inicialização do Iframe.")
            
            # 2. FORÇA ESPERA PELO CONTEÚDO DO JOGO
            try:
                # Foca o iframe
                driver.switch_to.default_content()
                driver.switch_to.frame(iframe) 
                
                # Espera que o elemento principal do histórico esteja na página (10 segundos)
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block, app-stats-widget"))
                )
                print(f"[{nome}] ✅ Elementos de leitura confirmados.")
                
            except TimeoutException:
                raise Exception("Timeout: Elementos de histórico não carregaram após 10s.")
            except Exception as e:
                raise Exception(f"Erro ao confirmar elementos: {e}")

            print(f"🚀 [{nome}] MONITORANDO EM '{path_fb}'")
            
            LAST_SENT = None
            ULTIMO_MULTIPLIER_TIME = time()
            
            # NOVO SELETOR: Garante que pegue o primeiro item da lista de históricos.
            # O "primeiro filho" (first-child) é geralmente o resultado mais recente CONCLUÍDO.
            # Estamos simplificando e priorizando a estrutura de lista de resultados.
            SELECTOR_MULTIPLIER = ".payouts-block .payout:first-child, app-stats-widget .bubble-multiplier:first-child"
            
            while True: # Loop Leitura
                now_br = datetime.now(TZ_BR)
                
                # REINÍCIO DIÁRIO: 00:00 a 00:05
                if now_br.hour == 0 and now_br.minute <= 5 and (relogin_date != now_br.date()):
                    print(f"🌙 [{nome}] Reinício diário.")
                    relogin_date = now_br.date()
                    raise Exception("Reinício Diário")

                if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                    raise Exception("Inatividade detectada")

                try:
                    # Garante foco no iframe
                    driver.switch_to.default_content()
                    driver.switch_to.frame(iframe) 
                    
                    payouts = driver.find_elements(By.CSS_SELECTOR, SELECTOR_MULTIPLIER)
                    
                    if not payouts:
                        # LOG DETALHADO: Ajuda a rastrear se o elemento sumiu
                        print(f"[{nome}] ❓ Payouts vazios. Tentando novamente.") 
                        sleep(POLLING_INTERVAL)
                        continue 
                    
                    raw_text = payouts[0].get_attribute("innerText")
                    clean_text = raw_text.strip().lower().replace('x', '')

                    if not clean_text:
                        sleep(POLLING_INTERVAL)
                        continue 

                    try:
                        novo = float(clean_text)
                    except ValueError:
                        sleep(POLLING_INTERVAL)
                        continue
                    
                    # LOG DE RASTREIO: Mostra o que ele leu, mesmo que não salve
                    # Se o ORIGINAL estiver lendo 1.00x repetidamente, isso irá aparecer
                    if nome == "ORIGINAL":
                         print(f"[{nome}] LIDO: {novo:.2f}x | ÚLTIMO SALVO: {LAST_SENT} | DIFERENTE?: {novo != LAST_SENT}")

                    
                    if novo != LAST_SENT:
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
                        except Exception as e:
                            pass

                    sleep(POLLING_INTERVAL)

                except (StaleElementReferenceException, NoSuchElementException) as e:
                    # Se o elemento morrer, tenta achar de novo o iframe
                    print(f"⚠️ [{nome}] Elemento perdido. Tentando recuperar Iframe...")
                    iframe_new = initialize_game_elements(driver, nome)
                    if iframe_new:
                        iframe = iframe_new
                        continue
                    else:
                        raise Exception("Iframe irrecuperável.")

                except Exception as e:
                    pass 

        except Exception as e:
            print(f"❌ [{nome}] Falha Crítica: {e}. Reiniciando em 10s...")
            if driver:
                try: driver.quit()
                except: pass
            sleep(10)

if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD.")
        sys.exit(1)
    
    print("==============================================")
    print("    GOATHBOT V6.8 - DUAL MONITORING (SELECTORS)")
    print("==============================================")

    threads = []
    for config in CONFIG_BOTS:
        t = threading.Thread(target=run_single_bot, args=(config,))
        t.start()
        threads.append(t)
        sleep(5) 

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n🚫 Interrompido.")
    except Exception as e:
        print(f"\n❌ Erro Geral: {e}")
