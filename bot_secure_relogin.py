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

# =============================================================
# 🔥 GOATHBOT V6.2 - DUAL MODE (SINGLE DRIVER) - CORRIGIDO
# =============================================================
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"

# CONFIGURAÇÃO DOS DOIS JOGOS
CONFIG_BOTS = [
    {
        "nome": "ORIGINAL",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator",
        "firebase_path": "history",
        "window_handle": None 
    },
    {
        "nome": "AVIATOR 2",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator-2",
        "firebase_path": "aviator2",
        "window_handle": None
    }
]

# Configuração Limpa de Logs
logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
TZ_BR = pytz.timezone("America/Sao_Paulo")

# Configurações Turbo
POLLING_INTERVAL = 0.05 # Rápido
TEMPO_MAX_INATIVIDADE = 360

# Variáveis Globais de Sincronização
DRIVER_LOCK = threading.Lock() 
GLOBAL_DRIVER = None           
RESTART_FLAG = False           

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

def start_driver():
    """Inicia o driver (apenas uma vez)."""
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
            # Fallback para ambientes de servidor
            return webdriver.Chrome(options=options)
        except Exception as e:
            print(f"❌ Erro ao iniciar driver: {e}")
            raise

def safe_click(driver, by, value, timeout=5):
    """Tenta clicar com WebDriverWait."""
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

def initial_login_and_setup(driver):
    """Faz o login (fora da thread, apenas uma vez)."""
    print("⏳ Acessando site e configurando abas...")
    
    driver.get(URL_DO_SITE)
    sleep(2)
    check_blocking_modals(driver)

    if safe_click(driver, By.XPATH, "//button[contains(., 'Entrar')]", 5) or \
       safe_click(driver, By.CSS_SELECTOR, 'a[href*="login"]', 5):
        sleep(1)
        try:
            driver.find_element(By.NAME, "email").send_keys(EMAIL)
            driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            if safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 5):
                sleep(5)
                print("✅ Login enviado.")
                return True
        except:
            print("❌ Falha no preenchimento do login.")
            return False
    
    print("❌ Falha ao encontrar botão de Login.")
    return False

def setup_tabs(driver, bots_config):
    """Navega para cada jogo em uma nova aba e armazena o handle."""
    for i, config in enumerate(bots_config):
        if i > 0:
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            
        driver.get(config["link"])
        sleep(5) 
        check_blocking_modals(driver)
        
        config["window_handle"] = driver.current_window_handle
        print(f"✅ Aba {config['nome']} ({config['firebase_path']}) configurada.")
        
    driver.switch_to.window(bots_config[0]["window_handle"])
    return True

def initialize_game_elements(driver, bot_config):
    """Localiza o iframe e o elemento de histórico APENAS para verificação inicial e foca a aba."""
    nome = bot_config["nome"]
    
    # 1. Troca o foco para a aba correta
    driver.switch_to.window(bot_config["window_handle"])
    
    # 2. Sai do iframe se estiver dentro
    try: driver.switch_to.default_content()
    except: pass
    
    try:
        print(f"[{nome}] Buscando Iframe para {nome}...")
        iframe = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'))
        )
        driver.switch_to.frame(iframe)
    except:
        return False # Falha ao encontrar Iframe

    try:
        print(f"[{nome}] Buscando Histórico...")
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block, app-stats-widget"))
        )
        print(f"[{nome}] Elementos de {nome} carregados com sucesso.")
    except:
        return False # Falha ao encontrar histórico

    return True

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
    """Função que roda o ciclo de vida de UM bot, sincronizando o acesso ao driver."""
    global GLOBAL_DRIVER, RESTART_FLAG
    
    nome = bot_config["nome"]
    path_fb = bot_config["firebase_path"]
    
    driver = GLOBAL_DRIVER
    
    LAST_SENT = None
    ULTIMO_MULTIPLIER_TIME = time()
    relogin_date = date.today()

    # Tenta carregar os elementos iniciais (usa o lock)
    with DRIVER_LOCK:
        try:
            if not initialize_game_elements(driver, bot_config): 
                raise Exception("Elementos críticos não encontrados na inicialização") 
            print(f"[{nome}] MONITORANDO: {nome}...")
        except Exception as e:
            print(f"❌ [{nome}] Falha crítica na inicialização: {e}. Setando flag de reinício.")
            RESTART_FLAG = True
            return

    while not RESTART_FLAG: # Loop de leitura
        try:
            # 1. Manutenção Diária e Inatividade
            now_br = datetime.now(TZ_BR)
            
            if now_br.hour == 0 and now_br.minute <= 5 and (relogin_date != now_br.date()):
                print(f"🌙 [{nome}] Reinício diário forçado. Setando flag de reinício.")
                relogin_date = now_br.date()
                RESTART_FLAG = True
                break 

            if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                print(f"❌ [{nome}] Inatividade detectada. Setando flag de reinício.")
                RESTART_FLAG = True
                break
                
            # 2. Acesso Sincronizado para Leitura (BLOCO CRÍTICO)
            with DRIVER_LOCK:
                # Troca para a aba correta
                driver.switch_to.window(bot_config["window_handle"])
                driver.switch_to.default_content()

                # Revalida e foca o iframe
                iframe_element = WebDriverWait(driver, 0.5).until( # Reduzindo espera para 0.5s
                    EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'))
                )
                driver.switch_to.frame(iframe_element)
                
                # REVALIDAÇÃO DO HISTÓRICO: Busca o elemento de histórico a cada ciclo
                hist = WebDriverWait(driver, 0.5).until( # Reduzindo espera para 0.5s
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block, app-stats-widget"))
                )

                # Leitura - Tenta ler o elemento dentro do elemento de histórico recém-validado
                first_payout = hist.find_element(By.CSS_SELECTOR, ".payout:first-child, .bubble-multiplier:first-child")
                raw_text = first_payout.get_attribute("innerText")
                clean_text = raw_text.strip().lower().replace('x', '')

            # FIM DO LOCK

            if not clean_text:
                sleep(POLLING_INTERVAL)
                continue 

            try:
                novo = float(clean_text)
            except ValueError:
                sleep(POLLING_INTERVAL)
                continue 
            
            # 3. Envio (FORA DO LOCK)
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
                    print(f"⚠️ [{nome}] Erro Firebase: {e}")

            sleep(POLLING_INTERVAL)

        except (StaleElementReferenceException, NoSuchElementException, WebDriverException, TimeoutException) as e:
            error_name = e.__class__.__name__
            print(f"⚠️ [{nome}] Erro de elemento ('{error_name}'). Tentando re-inicializar elementos (full)...")
            
            # Se o erro for de elemento/contexto, tentamos uma re-inicialização completa dos elementos
            with DRIVER_LOCK:
                if not initialize_game_elements(driver, bot_config):
                    # Se falhar, é crítica
                    print(f"❌ [{nome}] Falha crítica ao re-inicializar. Setando flag de reinício.")
                    RESTART_FLAG = True
                    break
            
            print(f"[{nome}] ✅ Re-inicialização bem-sucedida. Retomando o loop.")
            continue
                
        except Exception as e:
            print(f"❌ [{nome}] Erro inesperado: {e.__class__.__name__}. Setando flag de reinício.")
            RESTART_FLAG = True
            break
            
# =============================================================
# 🚀 EXECUTOR PRINCIPAL
# =============================================================
if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD nas variáveis de ambiente.")
        sys.exit(1)
    
    print("==============================================")
    print("    GOATHBOT V6.2 - SINGLE DRIVER MODE")
    print("==============================================")
    
    while True: # Loop de reinício completo
        GLOBAL_DRIVER = None
        RESTART_FLAG = False
        
        try:
            # 1. Inicializa o driver e faz o login uma vez
            GLOBAL_DRIVER = start_driver()
            if not initial_login_and_setup(GLOBAL_DRIVER):
                raise Exception("Falha no Login Inicial")

            # 2. Configura as abas
            if not setup_tabs(GLOBAL_DRIVER, CONFIG_BOTS):
                raise Exception("Falha na configuração das abas")
            
            print("==============================================")
            print("✅ Iniciando monitoramento paralelo (Aguardando LOCK)")
            
            # 3. Inicia as Threads
            threads = []
            for config in CONFIG_BOTS:
                t = threading.Thread(target=run_single_bot, args=(config,))
                t.start()
                threads.append(t)
            
            # Aguarda a conclusão das threads
            for t in threads:
                t.join()

            if RESTART_FLAG:
                print("\n\n>>> 🔄 REINICIANDO CICLO COMPLETO (Falha Crítica / Manutenção) <<<")
            
        except Exception as e:
            print(f"\n\n>>> ❌ ERRO CRÍTICO NO EXECUTOR: {e}. Reiniciando em 10s... <<<")
            RESTART_FLAG = True 
            
        finally:
            if GLOBAL_DRIVER:
                try: GLOBAL_DRIVER.quit()
                except: pass
            
            if RESTART_FLAG:
                sleep(10)
            else:
                break
