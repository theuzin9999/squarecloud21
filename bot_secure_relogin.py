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
# 🔥 CONFIGURAÇÃO GERAL
# =============================================================
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"
LINK_AVIATOR = "https://www.goathbet.com/pt/casino/spribe/aviator"

# Configuração de Logs para limpar o console
logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

# Credenciais do ambiente
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
TZ_BR = pytz.timezone("America/Sao_Paulo")

# ⚡ CONFIGURAÇÕES TURBO
POLLING_INTERVAL = 0.1          # Leitura ultra-rápida
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

# =============================================================
# 🛠️ DRIVER E NAVEGAÇÃO
# =============================================================
def start_driver():
    """Configuração otimizada para Servidor (Headless) + Performance"""
    options = webdriver.ChromeOptions()
    
    # Opções de Servidor (Essenciais para Square Cloud)
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless") 
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    # Opções de Performance
    options.page_load_strategy = 'eager'
    options.add_argument("--log-level=3")
    options.add_argument("--silent")
    options.add_argument("--disable-popup-blocking")

    try:
        # Tenta instalar driver automaticamente
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except:
        # Fallback para caminho linux padrão
        return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)

def safe_click(driver, by, value, timeout=5):
    try:
        element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        driver.execute_script("arguments[0].click();", element)
        return True
    except:
        return False

def check_blocking_modals(driver):
    """Fecha popups de +18 e Cookies que bloqueiam o clique"""
    try:
        # Botões de confirmação de idade
        xpaths = [
            "//button[contains(., 'Sim')]", 
            "//button[@data-age-action='yes']",
            "//div[contains(text(), '18')]/following::button[1]"
        ]
        for xp in xpaths:
            if safe_click(driver, By.XPATH, xp, 1): break
        
        # Aceitar cookies
        safe_click(driver, By.XPATH, "//button[contains(., 'Aceitar')]", 1)
    except: pass

def process_login(driver):
    print("➡️ Iniciando login (V5.1)...")
    try:
        driver.get(URL_DO_SITE)
    except TimeoutException: pass
    
    sleep(2)
    check_blocking_modals(driver)

    # --- CORREÇÃO DO ERRO DE LOGIN AQUI ---
    # Tenta múltiplos seletores para o botão "Entrar"
    login_clicked = False
    if safe_click(driver, By.XPATH, "//button[contains(., 'Entrar')]", 5):
        login_clicked = True
    elif safe_click(driver, By.CSS_SELECTOR, 'a[href*="login"]', 5):
        login_clicked = True
    elif safe_click(driver, By.XPATH, "//div[contains(text(), 'Entrar')]", 5):
        login_clicked = True

    if login_clicked:
        print("ℹ️ Modal de login aberto.")
        sleep(1)
        try:
            # Preenche campos (Tenta ID antigo e NAME novo)
            try: driver.find_element(By.NAME, "email").send_keys(EMAIL)
            except: driver.find_element(By.CSS_SELECTOR, "input[type='email']").send_keys(EMAIL)
            
            try: driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            except: driver.find_element(By.CSS_SELECTOR, "input[type='password']").send_keys(PASSWORD)

            # Botão confirmar
            if safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 4) or \
               safe_click(driver, By.XPATH, "//button[contains(., 'Entrar')]", 4):
                print("✅ Credenciais enviadas.")
                sleep(5)
        except Exception as e:
            print(f"⚠️ Falha ao preencher: {e}")
    else:
        print("⚠️ Botão de login não encontrado ou já logado. Seguindo...")

    print("➡️ Navegando para Aviator...")
    driver.get(LINK_AVIATOR)
    
    # Aguarda carregamento do iframe
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe")]'))
        )
    except:
        print("⚠️ Alerta: Iframe demorou a carregar.")
        
    check_blocking_modals(driver)
    return True

def initialize_game_elements(driver):
    """Busca elementos com prioridade no SPRIBE"""
    
    # PRIORIDADE MÁXIMA: SPRIBE
    POSSIVEIS_IFRAMES = [
        '//iframe[contains(@src, "spribe")]',
        '//iframe[contains(@src, "/aviator/")]',
        '//iframe[contains(@src, "game?token")]'
    ]
    
    POSSIVEIS_HISTORICOS = [
        ('.payouts-block', By.CSS_SELECTOR),  # Design novo
        ('.rounds-history', By.CSS_SELECTOR), # Fallback
        ('[data-testid="history"]', By.CSS_SELECTOR)
    ]

    driver.switch_to.default_content()
    iframe = None
    
    # Busca Iframe
    for xpath in POSSIVEIS_IFRAMES:
        try:
            iframe = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xpath)))
            driver.switch_to.frame(iframe)
            print(f"✅ Iframe conectado: {xpath}")
            break
        except:
            driver.switch_to.default_content()
            continue

    if not iframe: return None, None

    # Busca Histórico
    hist = None
    for selector, by_method in POSSIVEIS_HISTORICOS:
        try:
            hist = WebDriverWait(driver, 5).until(EC.presence_of_element_located((by_method, selector)))
            print(f"✅ Histórico detectado: {selector}")
            break
        except: continue

    if not hist:
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
# 🤖 LOOP PRINCIPAL (TURBO)
# =============================================================
def run_bot_session(relogin_done_for):
    driver = None
    try:
        driver = start_driver()
        process_login(driver) # Não encerra se falhar login, tenta ler mesmo assim

        iframe, hist = initialize_game_elements(driver)
        if not hist: raise Exception("Falha ao carregar elementos do jogo")

        print("✅ Robô Iniciado (V5.1 - Spribe Priority)\n")
        
        LAST_SENT = None
        ULTIMO_ENVIO = time()
        ULTIMO_MULTIPLIER_TIME = time()
        
        while True:
            # 1. Reinício Diário (00:00)
            now_br = datetime.now(TZ_BR)
            if now_br.hour == 0 and now_br.minute <= 5 and (relogin_done_for != now_br.date()):
                print(f"🕛 Reinício diário.")
                driver.quit()
                return now_br.date()

            # 2. Inatividade (6 min)
            if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                raise Exception("Inatividade - Reiniciando...")

            # 3. Leitura dos Multiplicadores
            try:
                resultados = []
                
                # Método 1: Itens individuais (Mais preciso)
                try:
                    items = hist.find_elements(By.CSS_SELECTOR, ".payouts-block .payout")
                    for it in items:
                        txt = it.text.strip().replace("x", "")
                        if txt: resultados.append(float(txt))
                except: pass

                # Método 2: Texto bruto (Fallback)
                if not resultados:
                    txt_full = hist.text.replace('x', '').replace('\n', ' ')
                    for val in txt_full.split():
                        try:
                            v = float(val)
                            if v >= 1.0: resultados.append(v)
                        except: pass

                # Processamento
                if resultados:
                    # Filtra duplicados mantendo ordem
                    seen = set()
                    resultados_unique = [x for x in resultados if not (x in seen or seen.add(x))]
                    
                    if resultados_unique:
                        novo = resultados_unique[0]
                        
                        if novo != LAST_SENT:
                            ULTIMO_MULTIPLIER_TIME = time()
                            now_br = datetime.now(TZ_BR)
                            raw = f"{novo:.2f}"
                            
                            # Salva no Firebase
                            entry = {
                                "multiplier": raw,
                                "time": now_br.strftime("%H:%M:%S"),
                                "color": getColorClass(novo),
                                "date": now_br.strftime("%Y-%m-%d")
                            }
                            entry_key = now_br.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                            
                            try:
                                db.reference(f"history/{entry_key}").set(entry)
                                print(f"🔥 {raw}x detectado.")
                                LAST_SENT = novo
                            except: pass

                sleep(POLLING_INTERVAL)

            except (StaleElementReferenceException, TimeoutException):
                # Reconexão rápida
                driver.switch_to.default_content()
                check_blocking_modals(driver)
                iframe, hist = initialize_game_elements(driver)
                if not hist: raise Exception("Perda de conexão com o jogo")

    except Exception as e:
        print(f"❌ Erro: {e}. Reiniciando...")
        if driver:
            try: driver.quit()
            except: pass
        raise e

# =============================================================
# 🛡️ START
# =============================================================
if __name__ == "__main__":
    print("==============================================")
    print("      GOATHBOT V5.1 (SERVIDOR + FIX LOGIN)")
    print("==============================================")
    
    if not EMAIL or not PASSWORD:
        print("❗ AVISO: EMAIL ou PASSWORD não configurados (Rodando sem login).")
    
    relogin_date = date.today()
    while True:
        try:
            nova = run_bot_session(relogin_date)
            if nova: relogin_date = nova
        except KeyboardInterrupt: break
        except:
            sleep(5)
