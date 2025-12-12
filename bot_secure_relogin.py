from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from time import sleep, time
from datetime import datetime, date
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, NoSuchElementException
import firebase_admin
from firebase_admin import credentials, db
import os
import pytz
import logging
import threading

# =============================================================
# 🔥 GOATHBOT V6.2 - DIAGNOSTIC EDITION
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

logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
TZ_BR = pytz.timezone("America/Sao_Paulo")

POLLING_INTERVAL = 1.0          
TEMPO_MAX_INATIVIDADE = 600     

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
    options.page_load_strategy = 'normal'
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--log-level=3")
    options.add_argument("--silent")

    try:
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except:
        return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)

def safe_click(driver, by, value, timeout=5):
    try:
        element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        driver.execute_script("arguments[0].click();", element)
        return True
    except: return False

def check_blocking_modals(driver):
    try:
        xpaths = [
            "//button[contains(., 'Sim')]", "//button[@data-age-action='yes']", 
            "//div[contains(text(), '18')]/following::button[1]", "//button[contains(., 'Aceitar')]",
            "//button[contains(@class, 'btn-primary')]", "//a[contains(@class, 'modal-close')]"
        ]
        for xp in xpaths:
            if safe_click(driver, By.XPATH, xp, 1): break
    except: pass

def process_login(driver, target_link):
    # Tenta ir direto para o jogo primeiro para ver se já está logado ou se redireciona
    try: driver.get(target_link)
    except: pass
    sleep(5)
    
    # Se tiver botão de login, faz login
    if len(driver.find_elements(By.XPATH, "//button[contains(., 'Entrar')]")) > 0 or \
       len(driver.find_elements(By.NAME, "email")) > 0:
        
        print(f"🔑 Realizando login...")
        try:
            # Garante que está na home ou na tela de login
            if "login" not in driver.current_url and "goathbet" in driver.current_url:
                 safe_click(driver, By.XPATH, "//button[contains(., 'Entrar')]", 3)
            
            WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.NAME, "email")))
            driver.find_element(By.NAME, "email").send_keys(EMAIL)
            driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
            sleep(5)
            
            # Navega novamente para o jogo após login
            print(f"🌍 Navegando para o jogo: {target_link}")
            driver.get(target_link)
            sleep(10)
        except Exception as e:
            print(f"⚠️ Erro no processo de login: {e}")

    check_blocking_modals(driver)
    return True

def initialize_game_elements(driver, bot_name):
    """
    Tenta localizar o iframe e o histórico.
    Se falhar, roda um DIAGNÓSTICO para listar o que está vendo.
    """
    try:
        driver.switch_to.default_content()
    except: pass
    
    iframe = None
    hist = None

    # 1. TENTATIVA DE ENCONTRAR IFRAME (Vários métodos)
    try:
        # A. Busca Específica (Padrão Spribe)
        iframe = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'))
        )
    except:
        try:
            # B. Busca Genérica (Qualquer iframe de jogo)
            iframe = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "game") or contains(@src, "launch") or contains(@class, "game")]'))
            )
        except:
            # C. DIAGNÓSTICO DE FALHA (Lista todos os iframes)
            print(f"\n🚫 [{bot_name}] NÃO ENCONTROU O IFRAME DO JOGO. RODANDO DIAGNÓSTICO:")
            try:
                all_iframes = driver.find_elements(By.TAG_NAME, "iframe")
                print(f"--- RELATÓRIO DE IFRAMES ({len(all_iframes)} encontrados) ---")
                for index, frame in enumerate(all_iframes):
                    src = frame.get_attribute("src")
                    visible = frame.is_displayed()
                    print(f"   [{index}] Visível: {visible} | SRC: {src[:80]}...") # Mostra os primeiros 80 chars
                print("-----------------------------------------------------------")
                
                # Tira Screenshot para debug visual
                file_name = f"debug_{bot_name.replace(' ', '_')}.png"
                driver.save_screenshot(file_name)
                print(f"📸 Screenshot salva como '{file_name}'")
                
            except Exception as diag_e:
                print(f"Erro no diagnóstico: {diag_e}")
            
            return None, None

    # Se achou o iframe, muda para ele
    try:
        driver.switch_to.frame(iframe)
    except:
        return None, None

    # 2. TENTATIVA DE ENCONTRAR HISTÓRICO
    try:
        hist = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block, app-stats-widget, .history-container, .last-results"))
        )
    except:
        print(f"🚫 [{bot_name}] Iframe acessado, mas container de histórico não encontrado.")
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
    nome = bot_config["nome"]
    link = bot_config["link"]
    path_fb = bot_config["firebase_path"]
    
    relogin_date = date.today()

    while True: 
        driver = None
        try:
            print(f"🔄 [{nome}] Iniciando navegador...")
            driver = start_driver()
            process_login(driver, link)

            # Passamos o nome para logging de erro
            iframe, hist = initialize_game_elements(driver, nome) 
            
            if not hist:
                print(f"❌ [{nome}] Falha: Elementos essenciais não encontrados. Reiniciando...")
                raise Exception("Elementos não encontrados")

            print(f"🚀 [{nome}] SISTEMA PRONTO -> Monitorando '{path_fb}'")
            
            LAST_SENT = None
            ULTIMO_MULTIPLIER_TIME = time()
            
            while True: 
                # 1. Manutenção Diária
                now_br = datetime.now(TZ_BR)
                if now_br.hour == 0 and now_br.minute <= 5 and (relogin_date != now_br.date()):
                    print(f"🌙 [{nome}] Reinício diário...")
                    driver.quit()
                    relogin_date = now_br.date()
                    break 

                # 2. Check Inatividade
                if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                    print(f"⚠️ [{nome}] Inatividade (>10min). Reiniciando...")
                    raise Exception("Inatividade")

                # 3. Leitura
                try:
                    # Tenta seletor padrão E alternativos
                    first_payout = WebDriverWait(hist, 2).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".payout:first-child, .bubble-multiplier:first-child, .item:first-child"))
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
                            print(f"🔥 [{nome}] CAPTURADO: {entry['multiplier']}x")
                            LAST_SENT = novo
                        except Exception as e:
                            print(f"⚠️ [{nome}] Erro Firebase: {e}")

                    sleep(POLLING_INTERVAL)

                except StaleElementReferenceException:
                    print(f"⚠️ [{nome}] Stale Element. Re-buscando...")
                    driver.switch_to.default_content()
                    iframe, hist = initialize_game_elements(driver, nome)
                    if not hist: raise Exception("Falha ao re-buscar elementos")
                
                except TimeoutException:
                    sleep(POLLING_INTERVAL)
                    continue

                except Exception as e:
                    print(f"⚠️ [{nome}] Erro leitura: {e}")
                    driver.switch_to.default_content()
                    iframe, hist = initialize_game_elements(driver, nome)
                    if not hist: raise Exception("Recuperação falhou")

        except Exception as e:
            print(f"❌ [{nome}] Restarting: {e}")
            if driver:
                try: driver.quit()
                except: pass
            sleep(10)

if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD nas variáveis de ambiente.")
    else:
        print("==============================================")
        print("    GOATHBOT V6.2 - DIAGNOSTIC MODE")
        print("==============================================")

        threads = []
        for config in CONFIG_BOTS:
            t = threading.Thread(target=run_single_bot, args=(config,))
            t.start()
            threads.append(t)
            sleep(5)

        for t in threads:
            t.join()
