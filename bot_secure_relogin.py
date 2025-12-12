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
# 🔥 GOATHBOT V6.4 - DUAL MONITORING (MAX ROBUSTEZ)
# =============================================================
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.io'
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

# Configurações Turbo
POLLING_INTERVAL = 0.05
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
    """Inicia um novo driver isolado para cada bot."""
    try:
        subprocess.run("taskkill /f /im chromedriver.exe", shell=True, check=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    except:
        pass 

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
            print(f"❌ [{nome_bot}] Erro ao iniciar driver: {e}. Verifique se o chromedriver está no PATH.")
            # Se a inicialização falhar, retorna None
            return None 

# Funções safe_click, check_blocking_modals, process_login, getColorClass... (sem alteração)
def safe_click(driver, by, value, timeout=5):
    """Tenta clicar com WebDriverWait e executa via JavaScript como fallback."""
    try:
        element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        try: element.click()
        except: driver.execute_script("arguments[0].click();", element)
        return True
    except: return False

def check_blocking_modals(driver):
    """Fecha popups chatos."""
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
    """Lógica de navegação e login para cada thread."""
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
    """Tenta localizar o iframe e o elemento de histórico."""
    try:
        driver.switch_to.default_content()
    except: pass
    
    iframe = None
    try:
        print(f"[{nome_bot}] 🔎 Buscando Iframe...")
        iframe = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'))
        )
        driver.switch_to.frame(iframe)
    except TimeoutException:
        print(f"[{nome_bot}] ❌ Timeout: Iframe não encontrado.")
        return None, None 
    except Exception as e:
        print(f"[{nome_bot}] ❌ Erro ao focar Iframe: {e}")
        return None, None

    hist = None
    try:
        print(f"[{nome_bot}] 🔎 Buscando Histórico...")
        hist = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block, app-stats-widget"))
        )
        print(f"[{nome_bot}] ✅ Elementos carregados.")
    except TimeoutException:
        print(f"[{nome_bot}] ❌ Timeout: Elemento de Histórico não encontrado.")
        return iframe, None 
    except Exception as e:
        print(f"[{nome_bot}] ❌ Erro ao buscar Histórico: {e}")
        return iframe, None

    # NOVO: Adicione uma verificação final antes de retornar
    if iframe is None or hist is None:
        return None, None
        
    return iframe, hist

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
    """Função que roda o ciclo de vida completo de UM bot em sua própria thread/driver."""
    nome = bot_config["nome"]
    link = bot_config["link"]
    path_fb = bot_config["firebase_path"]
    
    relogin_date = date.today()

    while True: # Loop infinito de reconexão/reinício
        driver = None
        try:
            print(f"\n🔄 [{nome}] Iniciando novo ciclo de driver...")
            driver = start_driver(nome)
            
            if driver is None:
                raise Exception("start_driver falhou ao retornar o driver.")
            
            if not process_login(driver, link):
                raise Exception("Falha no login ou navegação")

            # NOVO: Verificação defensiva antes de desempacotar
            elements = initialize_game_elements(driver, nome)
            if elements is None or len(elements) != 2:
                # O log de sucesso pode ter sido impresso, mas o retorno não foi a tupla.
                raise Exception("initialize_game_elements retornou resultado inválido ou None.")

            iframe, hist = elements

            if hist is None: 
                raise Exception("Elementos críticos (histórico) não encontrados na inicialização") 

            print(f"🚀 [{nome}] MONITORANDO EM '{path_fb}'")
            
            LAST_SENT = None
            ULTIMO_MULTIPLIER_TIME = time()
            
            while True: # Loop de leitura
                
                # 1. Manutenção Diária e Inatividade
                now_br = datetime.now(TZ_BR)
                
                if now_br.hour == 0 and now_br.minute <= 5 and (relogin_date != now_br.date()):
                    print(f"🌙 [{nome}] Reinício diário forçado.")
                    relogin_date = now_br.date()
                    raise Exception("Reinício Diário")

                if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                    raise Exception("Inatividade detectada")

                # 2. Leitura e Processamento
                try:
                    driver.switch_to.default_content()
                    driver.switch_to.frame(iframe) 
                    
                    first_payout = hist.find_element(By.CSS_SELECTOR, ".payout:first-child, .bubble-multiplier:first-child")
                    raw_text = first_payout.get_attribute("innerText")
                    clean_text = raw_text.strip().lower().replace('x', '')

                    if not clean_text:
                        sleep(POLLING_INTERVAL)
                        continue 

                    try:
                        novo = float(clean_text)
                    except ValueError:
                        sleep(POLLING_INTERVAL)
                        continue
                    
                    # 3. Envio
                    if novo != LAST_SENT:
                        ULTIMO_MULTIPLIER_TIME = time()
                        now_br = datetime.now(TZ_BR)
                        
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
                            print(f"⚠️ [{nome}] Erro Firebase: {e}")

                    sleep(POLLING_INTERVAL)

                except (StaleElementReferenceException, NoSuchElementException, WebDriverException) as e:
                    error_name = e.__class__.__name__
                    print(f"⚠️ [{nome}] Erro de elemento/driver ('{error_name}'). Tentando re-inicializar elementos...")
                    
                    # Tenta re-localizar apenas o iframe e o histórico
                    iframe_temp, hist_temp = initialize_game_elements(driver, nome)
                    
                    if hist_temp:
                        iframe, hist = iframe_temp, hist_temp
                        print(f"[{nome}] ✅ Re-inicialização bem-sucedida. Retomando o loop.")
                        continue
                    else: 
                        raise Exception(f"Falha crítica ao re-inicializar elementos após {error_name}.")
                    
                except Exception as e:
                    # Captura qualquer outro erro inesperado no loop de leitura
                    raise Exception(f"Erro inesperado no loop de leitura: {e}")

        except Exception as e:
            # Captura todas as falhas críticas (TypeError, Login, Inicialização, etc.)
            print(f"❌ [{nome}] Falha: {e.__class__.__name__} ({e}). Reiniciando driver em 7s...")
            if driver:
                try: driver.quit()
                except: pass
            sleep(7) # NOVO: Tempo de espera aumentado para garantir a limpeza dos processos

# =============================================================
# 🚀 EXECUTOR PARALELO
# =============================================================
if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD nas variáveis de ambiente.")
        sys.exit(1)
    
    print("==============================================")
    print("    GOATHBOT V6.4 - DUAL MONITORING (ROBUSTO)")
    print("==============================================")

    threads = []
    for config in CONFIG_BOTS:
        t = threading.Thread(target=run_single_bot, args=(config,))
        t.start()
        threads.append(t)
        sleep(3) 

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n🚫 Monitoramento interrompido pelo usuário (Ctrl+C).")
    except Exception as e:
        print(f"\n❌ ERRO NO EXECUTOR PRINCIPAL: {e}")
    
    print("✅ Programa encerrado.")
