import os
import logging
import threading
import pytz
import gc
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
# 🔥 GOATHBOT V6.5 - SERVER EDITION (FIX SELECTORS)
# =============================================================

# CONFIGURAÇÕES
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"
TZ_BR = pytz.timezone("America/Sao_Paulo")

# Variáveis de Ambiente
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

# CONFIGURAÇÃO DOS BOTS
CONFIG_BOTS = [
    {
        "nome": "AVIATOR_1",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator",
        "firebase_path": "history"
    },
    # =============================================================
    # 👇👇👇 APAGUE AS 3 ASPAS ABAIXO PARA VOLTAR O AVIATOR 2 👇👇👇
    """
    {
        "nome": "AVIATOR_2",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator-2",
        "firebase_path": "aviator2"
    }
    """
    # 👆👆👆 APAGUE AS 3 ASPAS ACIMA PARA VOLTAR O AVIATOR 2 👆👆👆
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
# 🛠️ DRIVER OTIMIZADO
# =============================================================
def start_driver():
    chrome_options = Options()
    
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1366,768")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--mute-audio")
    chrome_options.page_load_strategy = 'eager'

    # Otimizações de Memória
    chrome_options.add_argument("--js-flags=--max-old-space-size=1024")
    chrome_options.add_argument("--disable-features=RendererCodeIntegrity")

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
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, 'iframe')))
        return True
    except:
        return False

def get_game_elements(driver):
    try:
        driver.switch_to.default_content()
        
        # 1. Busca de IFRAME (Prioridade: Novo -> Antigo)
        potential_iframes = [
            "//iframe[contains(@class, 'game-iframe')]",              # Novo (via Classe)
            "//iframe[contains(@src, 'launch.spribegaming.com')]",    # Novo (via Link)
            "//iframe[contains(@src, 'spribe')]",                     # Antigo
            "//iframe[contains(@src, 'aviator')]"                     # Genérico
        ]

        iframe = None
        for xpath in potential_iframes:
            try:
                iframe = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, xpath))
                )
                if iframe: break
            except: continue
        
        if not iframe:
            print("⚠️ Iframe do jogo não encontrado.")
            return None

        driver.switch_to.frame(iframe)
        sleep(3) # 🔥 Aguarda o conteúdo do iframe renderizar (IMPORTANTE)

        # 2. Busca de HISTÓRICO (Prioridade: Visível -> Dropdown -> Antigo)
        potential_stats = [
            ".payouts-wrapper",                      # Barra fixa (visível na sua imagem)
            "app-stats-widget",                      # Container geral (seguro)
            "app-stats-dropdown .payouts-block",     # Dropdown (seu pedido, mas pode estar oculto)
            ".payouts-block",                        # Genérico
            ".result-history"                        # Container antigo
        ]

        hist = None
        for css_selector in potential_stats:
            try:
                hist = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
                )
                if hist: break
            except: continue

        if not hist:
            print("⚠️ Elemento de histórico interno não encontrado.")

        return hist
    except Exception as e:
        print(f"⚠️ Erro ao buscar elementos: {e}")
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
# 🤖 LOOP DA THREAD
# =============================================================
def run_bot_thread(config):
    if isinstance(config, str): return 

    nome = config['nome']
    link = config['link']
    path_fb = config['firebase_path']
    
    while True:
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
                print(f"⚠️ [{nome}] Falha Crítica: Jogo não carregou corretamente. Reiniciando...")
                if driver: driver.quit()
                continue

            # 🏥 HEALTH CHECK
            print(f"🏥 [{nome}] Verificando leitura de dados...")
            try:
                check_ok = False
                for _ in range(5): 
                    pre_text = driver.execute_script("return arguments[0].innerText;", hist_element)
                    # Verifica se tem pelo menos um número no texto
                    if pre_text and any(char.isdigit() for char in pre_text):
                        check_ok = True
                        break
                    sleep(2)
                
                if not check_ok:
                    raise Exception("Elemento encontrado mas está vazio")
            except Exception as e:
                print(f"⚠️ [{nome}] Falha no Health Check: {e}. Reiniciando...")
                if driver: driver.quit()
                continue 

            print(f"✅ [{nome}] Monitorando Ativo e Validado.")
            
            last_signature = [] 
            inactivity_timer = time()

            while True:
                # Reinício Diário
                now = datetime.now(TZ_BR)
                if now.hour == 23 and now.minute == 59:
                    print(f"🌙 [{nome}] Reinício Diário (23:59)...")
                    driver.quit()
                    gc.collect()
                    sleep(65)
                    break 

                if (time() - inactivity_timer) > 180:
                    print(f"⚠️ [{nome}] Sem dados novos há 3min. Reiniciando...")
                    break

                try:
                    text_data = driver.execute_script("return arguments[0].innerText;", hist_element)
                    
                    if text_data:
                        text_data = text_data.replace('x', '').replace('\n', ' ')
                        multipliers = []
                        
                        for val in text_data.split():
                            try:
                                v = float(val)
                                if v >= 1.0: multipliers.append(v)
                            except: pass

                        if multipliers:
                            current_signature = multipliers[:5]
                            
                            if current_signature != last_signature:
                                inactivity_timer = time()
                                last_signature = current_signature 
                                
                                newest = multipliers[0]
                                
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
            print(f"❌ [{nome}] Erro Geral: {e}")
            sleep(5)
        
        finally:
            if driver:
                try: driver.quit()
                except: pass
            gc.collect()
            sleep(5)

# =============================================================
# 🚀 EXECUÇÃO PRINCIPAL
# =============================================================
if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("⛔ Configure EMAIL e PASSWORD nas Variáveis de Ambiente!")
    else:
        init_firebase()
        active_bots = [b for b in CONFIG_BOTS if isinstance(b, dict)]
        
        threads = []
        print(f"🚀 Iniciando {len(active_bots)} Bots com LARGADA ESCALONADA...")
        
        for i, cfg in enumerate(active_bots):
            t = threading.Thread(target=run_bot_thread, args=(cfg,))
            t.start()
            threads.append(t)
            
            if i < len(active_bots) - 1:
                print(f"⏳ Aguardando 40s para iniciar o próximo bot...")
                sleep(40)
            
        for t in threads:
            t.join()
