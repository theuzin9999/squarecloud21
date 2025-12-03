from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from time import sleep, time
from datetime import datetime, date
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
import firebase_admin
from firebase_admin import credentials, db
import os
import pytz
import logging
import threading  # <--- NOVO: Essencial para rodar o envio sem bloquear
import sys # <--- ADICIONADO PARA SAÍDAS CRÍTICAS

# =============================================================
# 🔥 GOATHBOT V5.4 - FIX THREADING FIREBASE
# =============================================================
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"
LINK_AVIATOR = "https://www.goathbet.com/pt/casino/spribe/aviator"

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
# 🔧 FIREBASE E FUNÇÕES AUXILIARES
# =============================================================
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
    print("✅ Conexão Firebase estabelecida.")
except Exception as e:
    print(f"\n❌ ERRO CRÍTICO NO FIREBASE: {e}")
    print("⚠️ IMPORTANTE: Sua chave JSON é inválida ou expirou. Gere uma nova no console do Firebase!\n")
    sys.exit(1) # Sai se o Firebase falhar

def enviar_firebase_async(path, data):
    """Envia dados para o Firebase em uma thread separada (não bloqueia o loop principal)."""
    def _send():
        try:
            db.reference(path).set(data)
        except Exception as e:
            # Não é um erro crítico, apenas avisa que o envio falhou
            print(f"⚠️ Falha no envio Firebase: {e}")
    
    # Inicia o envio em uma nova thread
    threading.Thread(target=_send).start()

# =============================================================
# 🛠️ DRIVER E NAVEGAÇÃO
# ... (NÃO ALTERADO)
# =============================================================
def start_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless=new") # Recomenda-se a flag mais nova
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.page_load_strategy = 'eager'
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
            "//button[contains(., 'Aceitar')]"
        ]
        for xp in xpaths:
            if safe_click(driver, By.XPATH, xp, 1): break
    except: pass

def process_login(driver):
    print("➡️ Iniciando fluxo de login...")
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
                print("✅ Credenciais enviadas.")
                sleep(3)
        except: pass
    
    print("➡️ Abrindo Aviator Spribe...")
    driver.get(LINK_AVIATOR)
    
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe")]'))
        )
    except: pass
        
    check_blocking_modals(driver)
    return True

def initialize_game_elements(driver):
    driver.switch_to.default_content()
    
    iframe = None
    try:
        iframe = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe")]'))
        )
        driver.switch_to.frame(iframe)
        print(f"✅ Iframe Spribe Conectado.")
    except:
        try:
            iframe = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "aviator")]'))
            )
            driver.switch_to.frame(iframe)
        except:
            driver.switch_to.default_content()
            return None, None

    hist = None
    try:
        hist = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block, app-stats-widget")) # Adicionado seletor alternativo
        )
        print(f"✅ Histórico encontrado.")
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
# 🤖 MOTOR DO ROBÔ (V5.4)
# =============================================================
def run_bot_session(relogin_done_for):
    driver = None
    try:
        driver = start_driver()
        process_login(driver)

        iframe, hist = initialize_game_elements(driver)
        if not hist: raise Exception("Elementos do jogo não carregaram")

        print("\n🔥 GOATHBOT V5.4 OPERACIONAL (Non-Blocking Firebase)\n")
        
        LAST_SENT = None
        ULTIMO_MULTIPLIER_TIME = time()
        
        while True:
            # 1. Reinício Diário
            now_br = datetime.now(TZ_BR)
            if now_br.hour == 0 and now_br.minute <= 5 and (relogin_done_for != now_br.date()):
                driver.quit()
                return now_br.date()

            # 2. Inatividade (Checado a cada loop)
            if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                raise Exception("Inatividade detectada")

            # 3. Leitura Otimizada
            try:
                resultados = []
                try:
                    items = hist.find_elements(By.CSS_SELECTOR, ".payout, .bubble-multiplier")
                    for it in items:
                        txt = it.text.strip().replace("x", "")
                        if txt: resultados.append(float(txt))
                except: pass

                if not resultados:
                    txt_full = hist.text.replace('x', '').replace('\n', ' ')
                    for val in txt_full.split():
                        try:
                            v = float(val)
                            if v >= 1.0: resultados.append(v)
                        except: pass

                # 4. Envio
                if resultados:
                    # Lógica para pegar o valor mais recente e único
                    seen = set()
                    resultados_unique = [x for x in resultados if not (x in seen or seen.add(x))]
                    
                    if resultados_unique:
                        novo = resultados_unique[0]
                        
                        if novo != LAST_SENT:
                            # ATUALIZA O TIMER APENAS AQUI!
                            ULTIMO_MULTIPLIER_TIME = time()
                            now_br = datetime.now(TZ_BR)
                            
                            entry = {
                                "multiplier": f"{novo:.2f}",
                                "time": now_br.strftime("%H:%M:%S"),
                                "color": getColorClass(novo),
                                "date": now_br.strftime("%Y-%m-%d")
                            }
                            key = now_br.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                            
                            # 👇 NOVO: CHAMA A FUNÇÃO NÃO BLOQUEANTE
                            enviar_firebase_async(f"history/{key}", entry)
                            print(f"🔥 {entry['multiplier']}x salvo às {entry['time']} (Thread)")
                            LAST_SENT = novo

                sleep(POLLING_INTERVAL)

            except (StaleElementReferenceException, TimeoutException):
                # Tenta refocar o iframe e encontrar o histórico
                driver.switch_to.default_content()
                check_blocking_modals(driver)
                iframe, hist = initialize_game_elements(driver)
                if not hist: raise Exception("Conexão perdida")

    except Exception as e:
        print(f"❌ Sessão finalizada: {e}")
        if driver:
            try: driver.quit()
            except: pass
        # Volta para o loop principal do __main__ para iniciar uma nova sessão
        raise e

if __name__ == "__main__":
    print("==============================================")
    print("          INICIANDO GOATHBOT V5.4")
    print("==============================================")
    relogin_date = date.today()
    while True:
        try:
            relogin_date = run_bot_session(relogin_date)
            # Se run_bot_session retornar uma data, reiniciou com sucesso.
            if not relogin_date:
                relogin_date = date.today() # Se falhou/travou, apenas tenta novamente
        except KeyboardInterrupt: break
        except Exception: 
            # Se cair em um erro (Exception), espera 5s e tenta novamente
            sleep(5)
