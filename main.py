import os
import logging
import threading
import pytz
from time import sleep, time
from datetime import datetime, date
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
import firebase_admin
from firebase_admin import credentials, db

# =============================================================
# 🔥 GOATHBOT V6.0 - SERVER EDITION (FIX DE ESTABILIDADE)
# =============================================================

# CONFIGURAÇÕES
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
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

# Configuração de Logs
logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

# =============================================================
# 🔧 FIREBASE INIT
# =============================================================
def init_firebase():
    if not firebase_admin._apps:
        try:
            if not os.path.exists(SERVICE_ACCOUNT_FILE):
                print(f"❌ Erro: Arquivo {SERVICE_ACCOUNT_FILE} não encontrado!")
                exit(1)
            cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
            firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
            print("✅ Firebase Conectado.")
        except Exception as e:
            print(f"❌ Erro Crítico Firebase: {e}")
            exit(1)

# =============================================================
# 🛠️ DRIVER OTIMIZADO PARA SERVIDORES (FIX DE ALOCAÇÃO DE RAM)
# =============================================================
def start_driver():
    chrome_options = Options()
    
    # Flags vitais para rodar no Linux/Docker da Square Cloud
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage") # Reduz uso de RAM
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1366,768")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--mute-audio")
    chrome_options.page_load_strategy = 'eager'

    # NOVO FIX CRÍTICO para o BUG de 3GB: Limita a memória interna e threads
    chrome_options.add_argument("--js-flags=--max-old-space-size=1024") # Limita a RAM V8 para 1GB por processo
    chrome_options.add_argument("--disable-features=RendererCodeIntegrity")

    # FIX DE VERSÃO: Usa os binários instalados no servidor
    chrome_options.binary_location = "/usr/bin/chromium"
    
    try:
        service = Service("/usr/bin/chromedriver")
        return webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"⚠️ Erro Crítico ao Iniciar Driver: {e}")
        return None

def safe_click(driver, by, value, timeout=5):
    try:
        element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        driver.execute_script("arguments[0].click();", element)
        return True
    except: return False

def check_blocking_modals(driver):
    try:
        popups = [
            "//button[contains(., 'Sim')]", 
            "//button[contains(., 'Aceitar')]",
            "//div[@role='dialog']//button"
        ]
        for xp in popups:
            if safe_click(driver, By.XPATH, xp, 1): break
    except: pass

def process_login(driver, target_link):
    print("🔑 Iniciando Login...")
    try:
        driver.get(URL_DO_SITE)
        sleep(2)
        check_blocking_modals(driver)
        
        if safe_click(driver, By.XPATH, "//button[contains(text(), 'Entrar')]", 5) or \
           safe_click(driver, By.CSS_SELECTOR, "a[href*='login']", 5):
            sleep(1)
            driver.find_element(By.NAME, "email").send_keys(EMAIL)
            driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 5)
            sleep(3)
    except Exception as e:
        print(f"⚠️ Aviso Login: {e}")

    print(f"🎮 Navegando: {target_link}")
    driver.get(target_link)
    
    try:
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, 'iframe')))
        return True
    except:
        return False

def get_game_elements(driver):
    try:
        driver.switch_to.default_content()
        # Procura o iframe (Aviator)
        iframe = WebDriverWait(driver, 15).until( # Aumentei o timeout para 15s para ser mais tolerante ao travamento
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'))
        )
        driver.switch_to.frame(iframe)
        # Procura o histórico dentro do iframe
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
    
    while True: # Ciclo de vida do Driver (Para recuperação de erros)
        driver = None
        try:
            print(f"🔄 [{nome}] Iniciando...")
            driver = start_driver()
            if not driver: 
                sleep(10)
                continue

            process_login(driver, link)
            hist_element = get_game_elements(driver)
            
            if not hist_element:
                print(f"⚠️ [{nome}] Falha ao encontrar o histórico. Reiniciando...")
                if driver: driver.quit()
                continue

            print(f"✅ [{nome}] Monitorando Ativo.")
            
            last_value = None
            inactivity_timer = time()

            while True: # Ciclo de Leitura
                # ⏰ REINÍCIO 23:59 (PARA LIMPEZA DE RAM/CACHE)
                now = datetime.now(TZ_BR)
                if now.hour == 23 and now.minute == 59:
                    print(f"🌙 [{nome}] Reinício Diário (23:59)...")
                    driver.quit()
                    sleep(65)
                    break 

                # Inatividade (5 min)
                if (time() - inactivity_timer) > 300:
                    print(f"⚠️ [{nome}] Inatividade. Reiniciando...")
                    break

                try:
                    text_data = hist_element.get_attribute("innerText").replace('x', '').replace('\n', ' ')
                    multipliers = []
                    for val in text_data.split():
                        try:
                            v = float(val)
                            if v >= 1.0: multipliers.append(v)
                        except: pass

                    if multipliers:
                        newest = multipliers[0]
                        if newest != last_value:
                            inactivity_timer = time()
                            last_value = newest
                            
                            now_save = datetime.now(TZ_BR)
                            key = now_save.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                            data = {
                                "multiplier": f"{newest:.2f}",
                                "time": now_save.strftime("%H:%M:%S"),
                                "color": get_color_class(newest),
                                "date": now_save.strftime("%Y-%m-%d")
                            }
                            db.reference(f"{path_fb}/{key}").set(data)
                            print(f"🔥 [{nome}] {data['multiplier']}x")

                    sleep(1)

                except (StaleElementReferenceException, WebDriverException):
                    hist_element = get_game_elements(driver)
                    if not hist_element: break

        except Exception as e:
            print(f"❌ [{nome}] Erro: {e}")
            sleep(5)
        
        finally:
            if driver:
                try: driver.quit()
                except: pass
            sleep(5)

# =============================================================
# 🚀 EXECUÇÃO PRINCIPAL
# =============================================================
if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("⛔ Configure EMAIL e PASSWORD nas Variáveis de Ambiente da Square!")
    else:
        init_firebase()
        threads = []
        print(f"🚀 Iniciando {len(CONFIG_BOTS)} Bots com 3GB RAM otimizado...")
        
        for cfg in CONFIG_BOTS:
            t = threading.Thread(target=run_bot_thread, args=(cfg,))
            t.start()
            threads.append(t)
            sleep(5)
            
        for t in threads:
            t.join()
        "firebase_path": "history"
    },
    {
        "nome": "AVIATOR_2",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator-2",
        "firebase_path": "aviator2"
    }
]

# Configuração de Logs
logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

# =============================================================
# 🔧 FIREBASE INIT
# =============================================================
def init_firebase():
    if not firebase_admin._apps:
        try:
            if not os.path.exists(SERVICE_ACCOUNT_FILE):
                print(f"❌ Erro: Arquivo {SERVICE_ACCOUNT_FILE} não encontrado!")
                exit(1)
            cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
            firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
            print("✅ Firebase Conectado.")
        except Exception as e:
            print(f"❌ Erro Crítico Firebase: {e}")
            exit(1)

# =============================================================
# 🛠️ DRIVER OTIMIZADO PARA SERVIDORES (LINUX FIX)
# =============================================================
def start_driver():
    chrome_options = Options()
    
    # Flags vitais para rodar no Linux/Docker da Square Cloud
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage") # Reduz uso de RAM
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1366,768")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--mute-audio")
    chrome_options.page_load_strategy = 'eager'

    # SOLUÇÃO CRÍTICA PARA O ERRO DE VERSÃO:
    chrome_options.binary_location = "/usr/bin/chromium"
    
    try:
        # Usa o ChromeDriver compatível que está no PATH do servidor
        service = Service("/usr/bin/chromedriver")
        return webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"⚠️ Erro Crítico ao Iniciar Driver: {e}")
        return None

def safe_click(driver, by, value, timeout=5):
    try:
        element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        driver.execute_script("arguments[0].click();", element)
        return True
    except: return False

def check_blocking_modals(driver):
    try:
        popups = [
            "//button[contains(., 'Sim')]", 
            "//button[contains(., 'Aceitar')]",
            "//div[@role='dialog']//button"
        ]
        for xp in popups:
            if safe_click(driver, By.XPATH, xp, 1): break
    except: pass

def process_login(driver, target_link):
    print("🔑 Iniciando Login...")
    try:
        driver.get(URL_DO_SITE)
        sleep(2)
        check_blocking_modals(driver)
        
        if safe_click(driver, By.XPATH, "//button[contains(text(), 'Entrar')]", 5) or \
           safe_click(driver, By.CSS_SELECTOR, "a[href*='login']", 5):
            sleep(1)
            driver.find_element(By.NAME, "email").send_keys(EMAIL)
            driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 5)
            sleep(3)
    except Exception as e:
        print(f"⚠️ Aviso Login: {e}")

    print(f"🎮 Navegando: {target_link}")
    driver.get(target_link)
    
    try:
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, 'iframe')))
        return True
    except:
        return False

def get_game_elements(driver):
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
    
    while True: # Ciclo de vida do Driver (Para recuperação de erros)
        driver = None
        try:
            print(f"🔄 [{nome}] Iniciando...")
            driver = start_driver()
            if not driver: 
                sleep(10)
                continue

            process_login(driver, link)
            hist_element = get_game_elements(driver)
            
            if not hist_element:
                print(f"⚠️ [{nome}] Falha no carregamento. Tentando novamente...")
                if driver: driver.quit()
                continue

            print(f"✅ [{nome}] Monitorando Ativo.")
            
            last_value = None
            inactivity_timer = time()

            while True: # Ciclo de Leitura
                # ⏰ REINÍCIO 23:59 (PARA LIMPEZA DE RAM/CACHE)
                now = datetime.now(TZ_BR)
                if now.hour == 23 and now.minute == 59:
                    print(f"🌙 [{nome}] Reinício Diário (23:59)...")
                    driver.quit()
                    sleep(65) # Garante que o minuto 59 passe
                    break 

                # Inatividade (5 min)
                if (time() - inactivity_timer) > 300:
                    print(f"⚠️ [{nome}] Inatividade. Reiniciando...")
                    break

                try:
                    text_data = hist_element.get_attribute("innerText").replace('x', '').replace('\n', ' ')
                    multipliers = []
                    for val in text_data.split():
                        try:
                            v = float(val)
                            if v >= 1.0: multipliers.append(v)
                        except: pass

                    if multipliers:
                        newest = multipliers[0]
                        if newest != last_value:
                            inactivity_timer = time()
                            last_value = newest
                            
                            now_save = datetime.now(TZ_BR)
                            key = now_save.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                            data = {
                                "multiplier": f"{newest:.2f}",
                                "time": now_save.strftime("%H:%M:%S"),
                                "color": get_color_class(newest),
                                "date": now_save.strftime("%Y-%m-%d")
                            }
                            db.reference(f"{path_fb}/{key}").set(data)
                            print(f"🔥 [{nome}] {data['multiplier']}x")

                    sleep(1)

                except (StaleElementReferenceException, WebDriverException):
                    hist_element = get_game_elements(driver)
                    if not hist_element: break # Se perder o elemento, reinicia o driver

        except Exception as e:
            print(f"❌ [{nome}] Erro: {e}")
            sleep(5)
        
        finally:
            if driver:
                try: driver.quit()
                except: pass
            sleep(5)

# =============================================================
# 🚀 EXECUÇÃO PRINCIPAL
# =============================================================
if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("⛔ Configure EMAIL e PASSWORD nas Variáveis de Ambiente da Square!")
    else:
        init_firebase()
        threads = []
        print(f"🚀 Iniciando {len(CONFIG_BOTS)} Bots com 3GB RAM otimizado...")
        
        for cfg in CONFIG_BOTS:
            t = threading.Thread(target=run_bot_thread, args=(cfg,))
            t.start()
            threads.append(t)
            sleep(5)
            
        for t in threads:
            t.join()
               
