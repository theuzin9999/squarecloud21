import os
import logging
import threading
import pytz
from time import sleep, time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
import firebase_admin
from firebase_admin import credentials, db

# =============================================================
# 🔥 GOATHBOT V6.0 - SERVER EDITION (SQUARE CLOUD)
# =============================================================

# CONFIGURAÇÕES GERAIS
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com' # Confirme se esta URL está certa
URL_DO_SITE = "https://www.goathbet.com"
TZ_BR = pytz.timezone("America/Sao_Paulo")

# Variáveis de Ambiente (Configure na Square Cloud)
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

# CONFIGURAÇÃO DOS BOTS
CONFIG_BOTS = [
    {
        "nome": "AVIATOR_1",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator",
        "firebase_path": "history"
    },
    {
        "nome": "AVIATOR_2",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator-2",
        "firebase_path": "aviator2"
    }
]

# Configuração de Logs (Silencioso para performance)
logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

# =============================================================
# 🔧 FIREBASE INIT
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

# =============================================================
# 🛠️ DRIVER OPTIMIZADO PARA SERVIDORES (LINUX)
# =============================================================
def start_driver():
    chrome_options = Options()
    
    # Flags essenciais para rodar liso na Square Cloud/Linux com 3GB
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage") # Usa /tmp em vez de /dev/shm (vital para Docker)
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1366,768") # Resolução menor economiza RAM
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--mute-audio") # Economiza processamento
    chrome_options.page_load_strategy = 'eager' # Carrega mais rápido
    
    # Tenta usar o driver gerenciado
    try:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"⚠️ Erro ao iniciar driver: {e}")
        return None

def safe_click(driver, by, value, timeout=5):
    try:
        element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        driver.execute_script("arguments[0].click();", element)
        return True
    except: return False

def check_blocking_modals(driver):
    """Fecha popups e modais de idade"""
    try:
        # Lista otimizada de seletores comuns
        popups = [
            "//button[contains(., 'Sim')]", 
            "//button[contains(., 'Aceitar')]",
            "//div[@role='dialog']//button"
        ]
        for xp in popups:
            try:
                if safe_click(driver, By.XPATH, xp, 1): break
            except: pass
    except: pass

def process_login(driver, target_link):
    print("🔑 Iniciando Login...")
    try:
        driver.get(URL_DO_SITE)
        sleep(3)
        check_blocking_modals(driver)
        
        # Tenta clicar no botão de login
        if safe_click(driver, By.XPATH, "//button[contains(text(), 'Entrar')]", 5) or \
           safe_click(driver, By.CSS_SELECTOR, "a[href*='login']", 5):
            
            sleep(2)
            # Preenche formulário
            driver.find_element(By.NAME, "email").send_keys(EMAIL)
            driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            
            # Submit
            safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 5)
            sleep(5) # Espera login processar
    except Exception as e:
        print(f"⚠️ Aviso Login: {e}")

    # Vai para o jogo
    print(f"🎮 Navegando para: {target_link}")
    driver.get(target_link)
    
    # Aguarda iframe carregar
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, 'iframe'))
        )
        return True
    except:
        return False

def get_game_elements(driver):
    """Foca no iframe e busca o histórico"""
    try:
        driver.switch_to.default_content()
        iframe = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'))
        )
        driver.switch_to.frame(iframe)
        
        hist = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block, app-stats-widget"))
        )
        return hist
    except:
        return None

def get_color_class(value):
    try:
        m = float(value)
        if 1.0 <= m < 2.0: return "blue-bg"
        if 2.0 <= m < 10.0: return "purple-bg"
        if m >= 10.0: return "magenta-bg"
    except: pass
    return "default-bg"

# =============================================================
# 🤖 LOOP DA THREAD (BOT INDIVIDUAL)
# =============================================================
def run_bot_thread(config):
    nome = config['nome']
    link = config['link']
    path_fb = config['firebase_path']
    
    while True: # Loop Principal de Reconexão (Crash Recovery)
        driver = None
        try:
            print(f"🔄 [{nome}] Iniciando Sessão...")
            driver = start_driver()
            if not driver: raise Exception("Falha ao criar driver")

            process_login(driver, link)
            
            hist_element = get_game_elements(driver)
            if not hist_element: raise Exception("Elemento de histórico não encontrado")

            print(f"✅ [{nome}] Monitorando...")
            
            last_value = None
            inactivity_timer = time()

            # Loop de Leitura
            while True:
                # ⏰ REINÍCIO AUTOMÁTICO ÀS 23:59
                now = datetime.now(TZ_BR)
                if now.hour == 23 and now.minute == 59:
                    print(f"🌙 [{nome}] Reinício Agendado (23:59)...")
                    driver.quit()
                    sleep(65) # Espera passar o minuto 59 para não reiniciar em loop
                    break # Sai do loop interno, força reinício do driver

                # Checagem de Inatividade (5 min sem dados novos)
                if (time() - inactivity_timer) > 300:
                    print(f"⚠️ [{nome}] Inatividade detectada. Reiniciando...")
                    break

                try:
                    # Captura dados
                    text_data = hist_element.get_attribute("innerText").replace('x', '').replace('\n', ' ')
                    multipliers = []
                    
                    for val in text_data.split():
                        try:
                            v = float(val)
                            if v >= 1.0: multipliers.append(v)
                        except: pass

                    if multipliers:
                        newest = multipliers[0] # O mais recente é o primeiro
                        
                        if newest != last_value:
                            inactivity_timer = time() # Reset timer
                            last_value = newest
                            
                            # Envio Firebase
                            now_save = datetime.now(TZ_BR)
                            key = now_save.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                            data = {
                                "multiplier": f"{newest:.2f}",
                                "time": now_save.strftime("%H:%M:%S"),
                                "color": get_color_class(newest),
                                "date": now_save.strftime("%Y-%m-%d")
                            }
                            
                            db.reference(f"{path_fb}/{key}").set(data)
                            print(f"🔥 [{nome}] {data['multiplier']}x detected")

                    sleep(1) # Intervalo seguro para não estourar CPU

                except (StaleElementReferenceException, WebDriverException):
                    # Se o elemento ficar velho, tenta re-focar
                    hist_element = get_game_elements(driver)
                    if not hist_element: break # Se não achar, reinicia driver

        except Exception as e:
            print(f"❌ [{nome}] Erro: {e}")
        
        finally:
            if driver:
                try: driver.quit()
                except: pass
            sleep(5) # Espera antes de reiniciar

# =============================================================
# 🚀 EXECUÇÃO PRINCIPAL
# =============================================================
if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("⛔ Configure EMAIL e PASSWORD nas Variáveis de Ambiente!")
    else:
        init_firebase()
        
        threads = []
        print(f"🚀 Iniciando {len(CONFIG_BOTS)} Bots com 3GB RAM otimizado...")
        
        for cfg in CONFIG_BOTS:
            t = threading.Thread(target=run_bot_thread, args=(cfg,))
            t.start()
            threads.append(t)
            sleep(5) # Delay entre inícios para não sobrecarregar CPU no boot
            
        for t in threads:
            t.join()
        
