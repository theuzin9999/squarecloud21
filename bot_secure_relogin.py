from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from time import sleep, time
from datetime import datetime, date
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, NoSuchElementException # Importado NoSuch
import firebase_admin
from firebase_admin import credentials, db
import os
import pytz
import logging
import threading

# =============================================================
# 🔥 GOATHBOT V6.0 - DUAL MODE (SERVER EDITION)
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

# Configurações Turbo
POLLING_INTERVAL = 0.5          # Aumentado para 0.5s para reduzir a sobrecarga e chance de Stale
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

# =============================================================
# 🛠️ DRIVER E NAVEGAÇÃO
# =============================================================
def start_driver():
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

    try:
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except:
        # Fallback para servidores Linux (Render/Heroku/VPS)
        return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)

def safe_click(driver, by, value, timeout=5):
    try:
        element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        driver.execute_script("arguments[0].click();", element)
        return True
    except: return False

def check_blocking_modals(driver):
    """Fecha popups chatos"""
    try:
        xpaths = [
            "//button[contains(., 'Sim')]", 
            "//button[@data-age-action='yes']", 
            "//div[contains(text(), '18')]/following::button[1]",
            "//button[contains(., 'Aceitar')]"
        ]
        for xp in xpaths:
            if safe_click(driver, By.XPATH, xp, 1): break
    except: pass

def process_login(driver, target_link):
    # 1. Acessa Home e faz Login
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
        except: pass
    
    # 2. Navega para o jogo específico
    driver.get(target_link)
    
    try:
        # Aumentado o timeout para a visibilidade do iframe
        WebDriverWait(driver, 25).until( 
            EC.visibility_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'))
        )
    except TimeoutException:
        print(f"Timeout ao esperar pelo iframe em {target_link}")
    except Exception:
        pass # Não é crítico se falhar aqui, o initialize_game_elements vai tentar

        
    check_blocking_modals(driver)
    return True

def initialize_game_elements(driver):
    """Tenta localizar o iframe e o elemento de histórico."""
    try:
        driver.switch_to.default_content()
    except: pass
    
    iframe = None
    try:
        # Tenta novamente encontrar o iframe com 10s de timeout
        iframe = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'))
        )
        driver.switch_to.frame(iframe)
    except:
        return None, None

    hist = None
    try:
        # Aumentado o timeout para 15s para dar mais chance de encontrar o histórico
        hist = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block, app-stats-widget"))
        )
    except:
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
    """Função que roda o ciclo de vida completo de UM bot"""
    nome = bot_config["nome"]
    link = bot_config["link"]
    path_fb = bot_config["firebase_path"]
    
    relogin_date = date.today()

    while True: # Loop infinito de reconexão se cair
        driver = None
        try:
            print(f"🔄 [{nome}] Iniciando driver...")
            driver = start_driver()
            process_login(driver, link)

            iframe, hist = initialize_game_elements(driver)
            if not hist: 
                print(f"❌ [{nome}] Falha crítica: Não foi possível encontrar o histórico.")
                raise Exception("Elementos não encontrados") # Força o reinício

            print(f"🚀 [{nome}] MONITORANDO EM '{path_fb}'")
            
            LAST_SENT = None
            ULTIMO_MULTIPLIER_TIME = time()
            
            while True: # Loop de leitura
                # 1. Manutenção Diária
                now_br = datetime.now(TZ_BR)
                if now_br.hour == 0 and now_br.minute <= 5 and (relogin_date != now_br.date()):
                    print(f"🌙 [{nome}] Reinício diário...")
                    driver.quit()
                    relogin_date = now_br.date()
                    break # Sai do loop de leitura para reiniciar driver

                # 2. Check Inatividade (6 minutos sem novo multiplicador)
                if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                    raise Exception("Inatividade detectada")

                # 3. Leitura e Processamento (USANDO WebDriverWait para esperar o elemento)
                try:
                    # Tenta pegar apenas o primeiro multiplicador (mais recente)
                    # Usa um timeout curto (3s) para esperar que o elemento apareça no container 'hist'
                    first_payout = WebDriverWait(hist, 3).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".payout:first-child, .bubble-multiplier:first-child"))
                    )

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
                    
                    # 4. Envio
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

                except TimeoutException:
                    # É comum que o elemento não apareça imediatamente (jogo Aguardando). Apenas ignora e continua.
                    sleep(POLLING_INTERVAL)
                    continue
                except StaleElementReferenceException:
                    # O elemento 'hist' (o container) ficou obsoleto. Tentamos re-inicializar
                    print(f"⚠️ [{nome}] Stale Element Detectado. Tentando re-inicializar elementos...")
                    driver.switch_to.default_content()
                    iframe, hist = initialize_game_elements(driver)
                    
                    if not hist: 
                        raise Exception("Falha crítica ao re-inicializar elementos.")
                    
                    sleep(POLLING_INTERVAL)
                    continue
                except NoSuchElementException:
                    # O elemento principal de histórico sumiu
                    print(f"⚠️ [{nome}] NoSuchElement (Histórico). Tentando re-inicializar elementos...")
                    driver.switch_to.default_content()
                    iframe, hist = initialize_game_elements(driver)
                    
                    if not hist: 
                        raise Exception("Falha crítica ao re-inicializar elementos.")

                    sleep(POLLING_INTERVAL)
                    continue
                except Exception as e:
                    # Qualquer outra exceção inesperada, força a re-inicialização completa
                    print(f"⚠️ [{nome}] Erro de leitura inesperado ('{e.__class__.__name__}'). Tentando re-inicializar elementos...")
                    driver.switch_to.default_content()
                    iframe, hist = initialize_game_elements(driver)
                    
                    if not hist: 
                        raise Exception("Falha crítica ao re-inicializar elementos.")
                    
                    sleep(POLLING_INTERVAL)
                    continue

        except Exception as e:
            # Qualquer exceção que chega aqui (Inatividade, Falha Crítica, Login, etc.) força o reinício do driver
            print(f"❌ [{nome}] Falha: {e}. Reiniciando em 5s...")
            if driver:
                try: driver.quit()
                except: pass
            sleep(5)

# =============================================================
# 🚀 EXECUTOR PARALELO
# =============================================================
if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD nas variáveis de ambiente.")
    else:
        print("==============================================")
        print("    GOATHBOT V6.0 - DUAL MONITORING")
        print("==============================================")

        threads = []
        for config in CONFIG_BOTS:
            t = threading.Thread(target=run_single_bot, args=(config,))
            t.start()
            threads.append(t)
            sleep(2) # Pequena pausa entre o início de cada um para não sobrecarregar CPU

        # Mantém script principal rodando
        for t in threads:
            t.join()
