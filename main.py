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
# 🔥 GOATHBOT V6.4 - SERVER EDITION (FIX LOGIN & IFRAME)
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
    
    # ======================================================================
    # ⬇️ APAGUE AS ASPAS TRIPLAS (''' ACIMA E ABAIXO) PARA REATIVAR O BOT ⬇️
    # ======================================================================
    '''
    {
        "nome": "AVIATOR_2",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator-2",
        "firebase_path": "aviator2"
    }
    '''
    # ======================================================================
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
    chrome_options.page_load_strategy = 'normal' # Mudado para normal para garantir carregamento do login

    # Otimizações de Memória
    chrome_options.add_argument("--js-flags=--max-old-space-size=1024")
    chrome_options.add_argument("--disable-features=RendererCodeIntegrity")

    # Caminho Fixo Square Cloud
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
            "//div[@role='dialog']//button",
            "//button[@aria-label='Close']"
        ]
        for xp in popups:
            if safe_click(driver, By.XPATH, xp, 2): break
    except: pass

def process_login(driver, target_link):
    print("🔑 Acessando site principal...")
    try:
        driver.get(URL_DO_SITE)
        sleep(5) # Espera o site carregar scripts iniciais
        check_blocking_modals(driver)
        
        # Verifica se JÁ está logado (procura botão de depósito ou perfil)
        is_logged_in = False
        try:
            WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(@href, 'deposit')] | //div[contains(@class, 'balance')]"))
            )
            print("✅ Já estava logado! Pulando login.")
            is_logged_in = True
        except:
            pass

        if not is_logged_in:
            print("👤 Realizando Login...")
            if safe_click(driver, By.XPATH, "//button[contains(text(), 'Entrar')]", 5) or \
               safe_click(driver, By.CSS_SELECTOR, "a[href*='login']", 5):
                
                sleep(2)
                driver.find_element(By.NAME, "email").send_keys(EMAIL)
                driver.find_element(By.NAME, "password").send_keys(PASSWORD)
                safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 5)
                
                # ESPERA CRÍTICA: Aguarda o login completar DE VERDADE
                print("⏳ Aguardando autenticação...")
                sleep(8) 
                
                # Verifica se deu certo
                if "login" in driver.current_url:
                    print("⚠️ Aviso: URL ainda contém 'login'. Pode ter falhado.")

    except Exception as e:
        print(f"⚠️ Erro no fluxo de login: {e}")

    print(f"🎮 Indo para o jogo: {target_link}")
    driver.get(target_link)
    
    try:
        # Espera extra para o redirecionamento interno do jogo
        sleep(5)
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, 'iframe')))
        return True
    except:
        return False

def get_game_elements(driver):
    try:
        driver.switch_to.default_content()
        
        # 1. Busca pelo Iframe usando a CLASSE ESPECÍFICA fornecida e depois SRC
        iframe = WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "iframe.game-iframe, iframe[src*='spribe'], iframe[src*='aviator']"))
        )
        
        driver.switch_to.frame(iframe)
        
        # 2. Busca o Histórico dentro do iframe
        hist = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 
                "app-stats-widget, .payouts-block, .result-history, .payouts-wrapper"
            ))
        )
        return hist
    except Exception as e:
        # print(f"Debug Elementos: {e}") # Descomente se precisar debugar
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
    
    while True:
        driver = None
        try:
            print(f"🔄 [{nome}] Iniciando navegador...")
            driver = start_driver()
            if not driver: 
                sleep(10)
                continue

            process_login(driver, link)
            hist_element = get_game_elements(driver)
            
            if not hist_element:
                print(f"⚠️ [{nome}] Jogo não carregou (Iframe não achado). Tentando novamente...")
                if driver: driver.quit()
                continue

            # 🏥 HEALTH CHECK
            print(f"🏥 [{nome}] Validando leitura de dados...")
            try:
                check_ok = False
                for _ in range(5): 
                    pre_text = driver.execute_script("return arguments[0].innerText;", hist_element)
                    if pre_text and any(char.isdigit() for char in pre_text):
                        check_ok = True
                        break
                    sleep(2)
                
                if not check_ok:
                    raise Exception("Elemento encontrado mas está vazio (Dados não carregaram)")
            except Exception as e:
                print(f"⚠️ [{nome}] Falha na Validação: {e}. Reiniciando...")
                if driver: driver.quit()
                continue

            print(f"✅ [{nome}] Sincronizado e Operando.")
            
            last_value = None
            inactivity_timer = time()

            while True:
                # ⏰ REINÍCIO 23:59
                now = datetime.now(TZ_BR)
                if now.hour == 23 and now.minute == 59:
                    print(f"🌙 [{nome}] Reinício Diário (23:59)...")
                    driver.quit()
                    gc.collect()
                    sleep(65)
                    break 

                # ⚠️ Timeout de 180s
                if (time() - inactivity_timer) > 180:
                    print(f"⚠️ [{nome}] Sem novos dados há 3min. Reiniciando...")
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
        threads = []
        
        # Filtra apenas configurações válidas
        active_bots = [cfg for cfg in CONFIG_BOTS if isinstance(cfg, dict)]
        
        print(f"🚀 Iniciando {len(active_bots)} Bots...")
        
        for i, cfg in enumerate(active_bots):
            t = threading.Thread(target=run_bot_thread, args=(cfg,))
            t.start()
            threads.append(t)
            
            # Intervalo entre inicializações
            if i < len(active_bots) - 1:
                print(f"⏳ Aguardando 40s para iniciar o próximo bot...")
                sleep(40)
            
        for t in threads:
            t.join()
