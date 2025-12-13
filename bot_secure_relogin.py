from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
# =================================================================
from webdriver_manager.chrome import ChromeDriverManager
# =================================================================
from time import sleep, time
from datetime import datetime, date
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, TimeoutException
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

# =============================================================
# 🛠️ DRIVER E NAVEGAÇÃO
# =============================================================
def start_driver(nome_bot): # Recebe o nome para log
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

    # Tenta a instalação automática (mais robusto), usando o fallback com log.
    try:
        print(f"[{nome_bot}]    -> Tentando ChromeDriverManager (Busca automática)...")
        # Sem especificar a versão, confiando na checagem do WDM.
        # Se falhar na checagem, a exceção será capturada.
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except Exception as e_wdm:
        print(f"[{nome_bot}]    -> Falha no ChromeDriverManager: {e_wdm}")
        # Fallback para o caminho estático (Square Cloud usa /usr/bin/chromium-chromedriver)
        try:
            print(f"[{nome_bot}]    -> Tentando caminho estático /usr/bin/chromedriver...")
            return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)
        except Exception as e_static:
            print(f"[{nome_bot}]    -> Falha no caminho estático: {e_static}")
            raise Exception(f"Falha CRÍTICA ao iniciar o WebDriver em AMBOS os métodos.")


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
    
    # 2. Navega para o jogo específico (Com lógica de nova tentativa)
    try:
        driver.get(target_link)
        # Timeout aumentado para 15s para garantir que a página carregue com lentidão.
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'))
        )
    except TimeoutException:
        # Nova tentativa de navegação se o primeiro GET falhar/demorar
        print(f"    -> Alerta: Timeout no primeiro GET. Tentando novamente...")
        driver.get(target_link)
        try:
             WebDriverWait(driver, 15).until(
                 EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'))
             )
        except:
            pass # Deixa o initialize_game_elements cuidar da falha.

    check_blocking_modals(driver)
    return True

def initialize_game_elements(driver):
    try:
        driver.switch_to.default_content()
    except: pass
    
    iframe = None
    try:
        # Timeout aumentado de 10s para 15s
        iframe = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'))
        )
        driver.switch_to.frame(iframe)
    except:
        return None, None

    hist = None
    try:
        # Timeout aumentado de 5s para 10s
        hist = WebDriverWait(driver, 10).until(
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

    while True: 
        driver = None
        try:
            print(f"🔄 [{nome}] Iniciando driver...")
            driver = start_driver(nome) # Passa o nome
            process_login(driver, link)

            iframe, hist = initialize_game_elements(driver)
            if not hist: raise Exception("Elementos não encontrados")

            print(f"🚀 [{nome}] MONITORANDO EM '{path_fb}'")
            
            LAST_SENT = None
            ULTIMO_MULTIPLIER_TIME = time()
            
            while True: 
                # 1. Manutenção Diária (específica desta thread)
                now_br = datetime.now(TZ_BR)
                if now_br.hour == 0 and now_br.minute <= 5 and (relogin_date != now_br.date()):
                    print(f"🌙 [{nome}] Reinício diário...")
                    driver.quit()
                    relogin_date = now_br.date()
                    break 

                # 2. Check Inatividade
                if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                    raise Exception("Inatividade detectada")

                # 3. Leitura
                try:
                    resultados = []
                    # Tenta pegar itens individuais
                    try:
                        items = hist.find_elements(By.CSS_SELECTOR, ".payout, .bubble-multiplier")
                        for it in items:
                            txt = it.get_attribute("innerText").strip().replace("x", "")
                            if txt: resultados.append(float(txt))
                    except: pass

                    # Fallback Texto Bruto
                    if not resultados:
                        txt_full = hist.get_attribute("innerText").replace('x', '').replace('\n', ' ')
                        for val in txt_full.split():
                            try:
                                v = float(val)
                                if v >= 1.0: resultados.append(v)
                            except: pass

                    # 4. Envio
                    if resultados:
                        # Pega o primeiro valor (mais recente)
                        novo = resultados[0]
                        
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

                except (StaleElementReferenceException, TimeoutException):
                    driver.switch_to.default_content()
                    iframe, hist = initialize_game_elements(driver)
                    if not hist: raise Exception("Conexão perdida elemento")

        except Exception as e:
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
            # AUMENTO CRÍTICO: Espera de 10s para evitar sobrecarga de CPU na inicialização do 2º Chrome.
            sleep(10) 

        # Mantém script principal rodando
        for t in threads:
            t.join()
