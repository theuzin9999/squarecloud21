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
# 🔥 GOATHBOT V6.1 - DEBUG & STABILITY EDITION
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

# Configurações de Tempo
POLLING_INTERVAL = 1.0          # Verificação a cada 1s (mais estável que 0.1s)
TEMPO_MAX_INATIVIDADE = 600     # 10 minutos sem novos jogos = reinicia

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
    options.page_load_strategy = 'normal' # Mudado para 'normal' para garantir carregamento
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
    """Fecha popups chatos"""
    try:
        xpaths = [
            "//button[contains(., 'Sim')]", 
            "//button[@data-age-action='yes']", 
            "//div[contains(text(), '18')]/following::button[1]",
            "//button[contains(., 'Aceitar')]",
            "//button[contains(@class, 'btn-primary')]"
        ]
        for xp in xpaths:
            if safe_click(driver, By.XPATH, xp, 1): break
    except: pass

def process_login(driver, target_link):
    print(f"🔑 Tentando login para acessar {target_link}...")
    try: driver.get(URL_DO_SITE)
    except: pass
    sleep(3)
    check_blocking_modals(driver)

    # Tenta clicar no botão de entrar
    if safe_click(driver, By.XPATH, "//button[contains(., 'Entrar')]", 5) or \
       safe_click(driver, By.CSS_SELECTOR, 'a[href*="login"]', 5):
        sleep(1)
        try:
            driver.find_element(By.NAME, "email").send_keys(EMAIL)
            driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
            sleep(5) # Espera login processar
        except: pass
    
    print(f"🌍 Navegando para o jogo...")
    driver.get(target_link)
    sleep(10) # Espera robusta para o carregamento inicial da página do jogo
    check_blocking_modals(driver)
    return True

def initialize_game_elements(driver):
    """Localiza o iframe e o histórico com timeouts longos"""
    try:
        driver.switch_to.default_content()
    except: pass
    
    iframe = None
    try:
        # Busca genérica por iframe de jogo
        iframe = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'))
        )
        driver.switch_to.frame(iframe)
    except:
        return None, None

    hist = None
    try:
        # Tenta encontrar o bloco de histórico
        hist = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block, app-stats-widget, .history-container"))
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
    nome = bot_config["nome"]
    link = bot_config["link"]
    path_fb = bot_config["firebase_path"]
    
    relogin_date = date.today()

    while True: # Loop Principal (Driver)
        driver = None
        try:
            print(f"🔄 [{nome}] Iniciando navegador...")
            driver = start_driver()
            process_login(driver, link)

            iframe, hist = initialize_game_elements(driver)
            
            if not hist:
                print(f"❌ [{nome}] Falha: Histórico não encontrado na inicialização.")
                raise Exception("Elementos não encontrados")

            print(f"🚀 [{nome}] SISTEMA PRONTO -> Monitorando '{path_fb}'")
            
            LAST_SENT = None
            ULTIMO_MULTIPLIER_TIME = time()
            
            while True: # Loop de Leitura (1s)
                # 1. Manutenção Diária (00:00)
                now_br = datetime.now(TZ_BR)
                if now_br.hour == 0 and now_br.minute <= 5 and (relogin_date != now_br.date()):
                    print(f"🌙 [{nome}] Reinício diário agendado...")
                    driver.quit()
                    relogin_date = now_br.date()
                    break 

                # 2. Check Inatividade
                if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                    print(f"⚠️ [{nome}] Inatividade detectada (>10min). Reiniciando...")
                    raise Exception("Inatividade")

                # 3. Leitura com Debug
                try:
                    # Tenta achar o elemento dentro do histórico já capturado
                    # O seletor busca o primeiro filho (mais recente)
                    first_payout = WebDriverWait(hist, 2).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".payout:first-child, .bubble-multiplier:first-child"))
                    )
                    
                    raw_text = first_payout.get_attribute("innerText")
                    clean_text = raw_text.strip().lower().replace('x', '')

                    # --- DEBUG LOG (Para entender por que não captura) ---
                    # Descomente a linha abaixo se quiser ver TUDO que ele lê (pode poluir o log)
                    # print(f"🔍 [{nome}] DEBUG LIDO: '{clean_text}'") 
                    
                    if not clean_text:
                        # Elemento existe mas está vazio
                        sleep(POLLING_INTERVAL)
                        continue

                    try:
                        novo = float(clean_text)
                    except ValueError:
                        # Leu algo que não é número (ex: "Aguardando")
                        sleep(POLLING_INTERVAL)
                        continue
                    
                    # 4. Envio (Se for novo)
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
                    print(f"⚠️ [{nome}] Elemento obsoleto (Página atualizou?). Re-buscando...")
                    driver.switch_to.default_content()
                    iframe, hist = initialize_game_elements(driver)
                    if not hist: raise Exception("Falha ao re-buscar elementos")
                
                except TimeoutException:
                    # Timeout normal esperando o elemento aparecer
                    sleep(POLLING_INTERVAL)
                    continue

                except Exception as e:
                    print(f"⚠️ [{nome}] Erro genérico de leitura: {e}")
                    # Tenta recuperar elementos
                    driver.switch_to.default_content()
                    iframe, hist = initialize_game_elements(driver)
                    if not hist: raise Exception("Falha crítica recuperação")

        except Exception as e:
            print(f"❌ [{nome}] Erro Crítico/Restart: {e}")
            if driver:
                try: driver.quit()
                except: pass
            sleep(10) # Espera 10s antes de tentar abrir o navegador de novo

# =============================================================
# 🚀 EXECUTOR
# =============================================================
if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❗ ERRO: Configure as variáveis de ambiente EMAIL e PASSWORD no Square Cloud.")
    else:
        print("==============================================")
        print("    GOATHBOT V6.1 - MONITORAMENTO DUPLO")
        print("==============================================")

        threads = []
        for config in CONFIG_BOTS:
            t = threading.Thread(target=run_single_bot, args=(config,))
            t.start()
            threads.append(t)
            sleep(5) # Delay entre inicialização dos bots para não travar CPU

        for t in threads:
            t.join()
