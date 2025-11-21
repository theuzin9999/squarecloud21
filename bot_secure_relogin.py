from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from time import sleep, time
from datetime import datetime, date
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
import firebase_admin
from firebase_admin import credentials, db
import os
import pytz
import logging

# =============================================================
# 🔥 CONFIGURAÇÃO GERAL & AMBIENTE
# =============================================================
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"
LINK_AVIATOR = "https://www.goathbet.com/pt/casino/spribe/aviator"

# Configuração de Logs
logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

# Credenciais
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
TZ_BR = pytz.timezone("America/Sao_Paulo")

# ⚡ CONFIGURAÇÕES DE VELOCIDADE (TURBO)
POLLING_INTERVAL = 0.1          # 10 checagens por segundo
INTERVALO_MINIMO_ENVIO = 0.1    # Envio imediato
TEMPO_MAX_INATIVIDADE = 360     # 6 minutos

# =============================================================
# 🔧 INICIALIZAÇÃO FIREBASE
# =============================================================
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
    print("✅ Firebase conectado.")
except Exception as e:
    print(f"❌ ERRO FIREBASE: {e}")
    # Em produção, talvez queira exit() aqui se o firebase for crucial

# =============================================================
# 🛠️ FUNÇÕES DE NAVEGAÇÃO E DRIVER
# =============================================================
def start_driver():
    """
    Configuração Híbrida:
    - Opções Headless (para servidor/cloud do arquivo antigo)
    - Opções de Performance (Eager/Logs do arquivo novo)
    """
    options = webdriver.ChromeOptions()
    
    # --- Otimizações de Performance (Do novo script) ---
    options.page_load_strategy = 'eager' 
    options.add_argument("--log-level=3")
    options.add_argument("--silent")
    
    # --- Configurações de Servidor/Headless (Do script antigo) ---
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--headless")  # Mantenha headless para servidor
    options.add_argument("--window-size=1920,1080")
    
    # Tenta usar o ChromeDriverManager (mais compatível). 
    # Se seu servidor exigir caminho fixo, altere service=...
    try:
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except:
        # Fallback para caminho fixo comum em VPS linux (se o manager falhar)
        service = Service("/usr/lib/chromium-browser/chromedriver")
        return webdriver.Chrome(service=service, options=options)

def safe_click(driver, by, value, timeout=5):
    try:
        element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        driver.execute_script("arguments[0].click();", element)
        return True
    except:
        return False

def check_blocking_modals(driver):
    """Fecha modais críticos (+18 e Cookies) - Lógica atualizada"""
    try:
        xpath_18 = [
            "//button[contains(., 'Sim')]", 
            "//div[contains(text(), '18 anos')]/..//button[contains(., 'Sim')]",
            "//button[contains(@class, 'MuiButton') and contains(., 'Sim')]",
            "//button[@data-age-action='yes']"
        ]
        for xpath in xpath_18:
            if safe_click(driver, By.XPATH, xpath, 1):
                sleep(0.5)
                break
        safe_click(driver, By.XPATH, "//button[contains(., 'Aceitar todos')]", 1)
        safe_click(driver, By.XPATH, "//button[contains(., 'Aceitar')]", 1)
    except: pass

def process_login(driver):
    print("➡️ Executando login (Fluxo Atualizado)...")
    try:
        driver.get(URL_DO_SITE)
    except TimeoutException: pass
    
    sleep(3)
    check_blocking_modals(driver)

    # Tenta abrir modal de login
    print("ℹ️ Tentando abrir modal de login...")
    if safe_click(driver, By.CSS_SELECTOR, 'button[aria-label="Entrar"]', 5) or \
       safe_click(driver, By.XPATH, "//button[contains(., 'Entrar')]", 5) or \
       safe_click(driver, By.CSS_SELECTOR, 'a[data-ix="window-login"]', 5):
        
        sleep(1)
        try:
            # Tenta preencher campos (suporta ID antigo e NAME novo)
            email_field = None
            try: email_field = driver.find_element(By.NAME, "email")
            except: email_field = driver.find_element(By.ID, "field-15") # ID antigo
            
            pass_field = None
            try: pass_field = driver.find_element(By.NAME, "password")
            except: pass_field = driver.find_element(By.ID, "password-login") # ID antigo

            if email_field and pass_field:
                email_field.send_keys(EMAIL)
                pass_field.send_keys(PASSWORD)
                
                # Botão de envio
                if safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 4) or \
                   safe_click(driver, By.CSS_SELECTOR, "a[login-btn]", 4):
                    print("✅ Login enviado.")
                    sleep(5)
            check_blocking_modals(driver)
        except Exception as e:
            print(f"⚠️ Erro no preenchimento: {e}")
    
    print("ℹ️ Navegando direto para Aviator Spribe...")
    driver.get(LINK_AVIATOR)
    
    # Aguarda iframe carregar
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe")]'))
        )
    except:
        print("⚠️ Timeout aguardando iframe principal.")
        
    check_blocking_modals(driver)
    return True

def initialize_game_elements(driver):
    """
    Localiza elementos com PRIORIDADE ATUALIZADA.
    Prioridade 1: Spribe / .payouts-block
    """
    
    # ORDEM DE PRIORIDADE ALTERADA CONFORME SOLICITADO
    POSSIVEIS_IFRAMES = [
        '//iframe[contains(@src, "spribe")]',        # Prioridade Máxima
        '//iframe[contains(@src, "/aviator/")]',
        '//iframe[contains(@src, "game?token")]',
        # Antigo como fallback final
        '//iframe[contains(translate(@src,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"salsagator")]'
    ]
    
    POSSIVEIS_HISTORICOS = [
        ('.payouts-block', By.CSS_SELECTOR),         # Prioridade Máxima
        ('div.payouts-block', By.CSS_SELECTOR),
        ('.rounds-history', By.CSS_SELECTOR),
        ('[data-testid="history"]', By.CSS_SELECTOR),
        ('.multipliers-history', By.CSS_SELECTOR)
    ]

    driver.switch_to.default_content()
    iframe = None
    
    for xpath in POSSIVEIS_IFRAMES:
        try:
            iframe = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xpath)))
            driver.switch_to.frame(iframe)
            print(f"✅ Iframe encontrado: {xpath}")
            break
        except:
            driver.switch_to.default_content()
            continue

    if not iframe:
        print("⚠️ Iframe não encontrado.")
        return None, None

    hist = None
    for selector, by_method in POSSIVEIS_HISTORICOS:
        try:
            hist = WebDriverWait(driver, 5).until(EC.presence_of_element_located((by_method, selector)))
            print(f"✅ Histórico encontrado: {selector}")
            break
        except: continue

    if not hist:
        print("⚠️ Histórico não encontrado.")
        driver.switch_to.default_content()
        return None, None

    return iframe, hist

def getColorClass(value):
    m = float(value)
    if 1.0 <= m < 2.0: return "blue-bg"
    if 2.0 <= m < 10.0: return "purple-bg"
    if m >= 10.0: return "magenta-bg"
    return "default-bg"

# =============================================================
# 🤖 MOTOR DO ROBÔ (Lógica Otimizada)
# =============================================================
def run_bot_session(relogin_done_for):
    driver = None
    try:
        driver = start_driver()
        if not process_login(driver):
            raise Exception("Erro no Login")

        iframe, hist = initialize_game_elements(driver)
        if not hist:
            raise Exception("Erro Elementos Jogo")

        print("✅ Captura TURBO iniciada (Spribe Priority).\n")
        
        LAST_SENT = None
        ULTIMO_ENVIO = time()
        ULTIMO_MULTIPLIER_TIME = time()
        
        while True:
            # 1. Reinício Diário (00:00)
            now_br = datetime.now(TZ_BR)
            if now_br.hour == 0 and now_br.minute <= 5 and (relogin_done_for != now_br.date()):
                print(f"🕛 Reinício diário programado.")
                driver.quit()
                return now_br.date()

            # 2. Checagem de Inatividade
            if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                print("🚨 Sem resultados há 6 min. Reiniciando...")
                raise Exception("Inatividade")

            # 3. LEITURA RÁPIDA
            try:
                resultados = []
                
                # Tenta ler itens individuais (payouts-block)
                try:
                    items = hist.find_elements(By.CSS_SELECTOR, ".payouts-block .payout")
                    if items:
                        for it in items:
                            txt = (it.text or "").strip().replace("x", "")
                            if txt:
                                try:
                                    v = float(txt)
                                    if v >= 1.0: resultados.append(v)
                                except: pass
                except: pass

                # Fallback texto se items falhar
                if not resultados:
                    txt_full = hist.text.replace('x', '').replace('\n', ' ')
                    for val in txt_full.split():
                        try:
                            v = float(val)
                            if v >= 1.0: resultados.append(v)
                        except: pass

                # 4. PROCESSAMENTO
                if resultados:
                    # Remove duplicatas mantendo ordem
                    seen = set()
                    resultados_unique = [x for x in resultados if not (x in seen or seen.add(x))]
                    
                    if resultados_unique:
                        novo = resultados_unique[0]
                        
                        if novo != LAST_SENT:
                            ULTIMO_MULTIPLIER_TIME = time() # Atualiza tempo de vida
                            
                            now_br = datetime.now(TZ_BR)
                            raw = f"{novo:.2f}"
                            entry_key = now_br.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                            time_display = now_br.strftime("%H:%M:%S")
                            
                            entry = {
                                "multiplier": raw,
                                "time": time_display,
                                "color": getColorClass(novo),
                                "date": now_br.strftime("%Y-%m-%d")
                            }
                            
                            try:
                                db.reference(f"history/{entry_key}").set(entry)
                                print(f"🔥 {raw}x salvo às {time_display}")
                                LAST_SENT = novo
                                ULTIMO_ENVIO = time()
                            except Exception as e: 
                                print(f"⚠️ Erro DB: {e}")

                sleep(POLLING_INTERVAL)

            except (StaleElementReferenceException, TimeoutException, WebDriverException):
                print("⚠️ Elementos perdidos. Reconectando...")
                driver.switch_to.default_content()
                check_blocking_modals(driver)
                iframe, hist = initialize_game_elements(driver)
                if not hist: raise Exception("Falha na reconexão")

    except Exception as e:
        print(f"❌ Sessão encerrada: {e}")
        if driver:
            try: driver.quit()
            except: pass
        raise e

# =============================================================
# 🛡️ GUARDIÃO
# =============================================================
def run_guardian():
    print("\n==============================================")
    print("      GOATHBOT V5.0 (SERVER + TURBO)")
    print("==============================================")
    relogin_date = date.today()
    
    while True:
        try:
            nova = run_bot_session(relogin_date)
            if nova: relogin_date = nova
        except KeyboardInterrupt: break
        except:
            print("🔄 Reiniciando em 5s...")
            sleep(5)

if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD nas variáveis de ambiente.")
    else:
        run_guardian()
