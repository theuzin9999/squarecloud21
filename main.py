import os
import logging
import threading
import pytz
import gc
import requests
from time import sleep, time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException, NoSuchElementException
import firebase_admin
from firebase_admin import credentials, db

# =============================================================
# 🔥 GOATHBOT V7.2 - FIX VELAS ALTAS
# =============================================================

# CONFIGURAÇÕES GERAIS
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"
TZ_BR = pytz.timezone("America/Sao_Paulo")

# Variáveis de Ambiente
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

# =============================================================
# 🤖 CONFIGURAÇÃO DOS BOTS (MODO EDITÁVEL)
# =============================================================

# 1. Este é o Bot que está funcionando AGORA (Aviator 1)
CONFIG_BOTS = [
    {
        "nome": "AVIATOR_1",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator",
        "firebase_path": "history"
    }
]

CONFIG_BOTS.append({
    "nome": "AVIATOR_2",
    "link": "https://www.goathbet.com/casino/spribe/aviator-vip",
    "firebase_path": "aviator2"
})

# Configuração de Logs
logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

# =============================================================
# 🔎 DIAGNÓSTICO DE REDE
# =============================================================
def run_diagnostics():
    print("\n--- 🕵️ DIAGNÓSTICO DE CONEXÃO ---")
    try:
        ip = requests.get('https://api.ipify.org', timeout=10).text
        print(f"🌐 IP Público: {ip}")
        res = requests.get(URL_DO_SITE, timeout=10)
        print(f"📡 Status Site: {res.status_code}")
    except Exception as e:
        print(f"⚠️ Alerta de Rede: {e}")
    print("----------------------------------\n")

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
    options = Options()
    options.page_load_strategy = 'eager'
    options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")
    options.add_argument("--disable-extensions")
    options.add_argument("--mute-audio")
    
    # User-Agent mais genérico
    options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36")
    
    # Opções anti-detecção
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    # Caminho Fixo Square Cloud / Linux
    options.binary_location = "/usr/bin/chromium"
    
    try:
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)
        # Oculta selenium
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """
        })
        return driver
    except Exception as e:
        print(f"⚠️ Erro Crítico ao Iniciar Driver: {e}")
        return None

# =============================================================
# 🔑 LOGIN ROBUSTO
# =============================================================
def process_login(driver, target_link):
    print("🔑 Iniciando Login...")
    try:
        driver.get(URL_DO_SITE)
        sleep(5)
        
        botoes_fechar = [
            "//button[contains(., 'Sim')]", 
            "//button[contains(., 'Aceitar')]", 
            "//button[contains(., 'Fechar')]",
            "//div[@role='dialog']//button"
        ]
        
        for xpath in botoes_fechar:
            try:
                btns = driver.find_elements(By.XPATH, xpath)
                for btn in btns:
                    if btn.is_displayed(): btn.click()
            except: pass

        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Entrar')]"))).click()
        sleep(2)
        driver.find_element(By.NAME, "email").send_keys(EMAIL)
        driver.find_element(By.NAME, "password").send_keys(PASSWORD)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        print("✅ Login enviado.")
        sleep(10) 
    except Exception as e:
        print(f"⚠️ Aviso Login: {e}")

    print(f"🎮 Navegando: {target_link}")
    driver.get(target_link)
    sleep(8)
    
    try:
        WebDriverWait(driver, 40).until(EC.presence_of_element_located((By.TAG_NAME, 'iframe')))
        return True
    except Exception as e:
        print(f"⚠️ iframe não encontrado: {e}")
        return False

# =============================================================
# 🎮 CAPTURA DE ELEMENTOS
# =============================================================
def get_game_elements(driver):
    try:
        driver.switch_to.default_content()
        iframe = WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.XPATH, "//iframe[contains(@src, 'spribegaming') or contains(@src, 'aviator')]"))
        )
        driver.switch_to.frame(iframe)
        hist = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block, .payouts-wrapper, [appcoloredmultiplier]"))
        )
        return hist
    except Exception as e:
        print(f"⚠️ Erro busca histórico: {e}")
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

            if not process_login(driver, link):
                print(f"⚠️ [{nome}] Falha no Login/Nav. Reiniciando...")
                driver.quit()
                sleep(5)
                continue

            hist_el = get_game_elements(driver)
            
            if not hist_el:
                print(f"⚠️ [{nome}] Falha ao encontrar histórico. Reiniciando...")
                if driver: driver.quit()
                continue

            print(f"✅ [{nome}] Monitorando Ativo.")
            
            last_val = None
            inactivity_timer = time()

            while True:
                # ⏰ REINÍCIO 23:59
                now = datetime.now(TZ_BR)
                if now.hour == 23 and now.minute == 59:
                    print(f"🌙 [{nome}] Reinício Diário (23:59)...")
                    break 

                # ⚠️ Timeout de Inatividade (6 min)
                if (time() - inactivity_timer) > 360:
                    print(f"⚠️ [{nome}] Sem dados novos há 6min. Reiniciando Driver...")
                    break

                try:
                    try:
                        first_payout = hist_el.find_element(By.CSS_SELECTOR, "[appcoloredmultiplier].payout:first-child, .payout:first-child, .bubble-multiplier:first-child")
                        raw = first_payout.get_attribute("innerText")
                    except:
                        raw = None
                    
                    if raw:
                        # -----------------------------------------------------------
                        # 🔥 CORREÇÃO AQUI: Remove vírgulas para velas > 1000x
                        # Ex: "1,540.20x" vira "1540.20"
                        # -----------------------------------------------------------
                        clean = raw.strip().lower().replace('x', '').replace(',', '')
                        
                        if clean:
                            try:
                                # Tenta converter para float
                                val_float = float(clean)
                                
                                # Usa o valor limpo para comparação
                                newest = clean 
                                
                                if newest != last_val:
                                    inactivity_timer = time()
                                    last_val = newest
                                    
                                    now_save = datetime.now(TZ_BR)
                                    key = now_save.strftime("%Y-%m-%d_%H-%M-%S")
                                    
                                    data = {
                                        "multiplier": f"{val_float:.2f}",
                                        "time": now_save.strftime("%H:%M:%S"),
                                        "color": get_color_class(val_float),
                                        "date": now_save.strftime("%Y-%m-%d")
                                    }
                                    
                                    db.reference(f"{path_fb}/{key}").set(data)
                                    print(f"🔥 [{nome}] {data['multiplier']}x")
                                    
                            except ValueError:
                                print(f"⚠️ [{nome}] Erro de formato no valor: '{raw}'")
                                pass 

                    sleep(1)

                except (StaleElementReferenceException, NoSuchElementException):
                    hist_el = get_game_elements(driver)
                    if not hist_el: break

        except Exception as e:
            print(f"❌ [{nome}] Erro Geral: {e}")
            sleep(5)
        
        finally:
            if driver:
                try: driver.quit()
                except: pass
            gc.collect()
            print(f"💤 [{nome}] Reiniciando ciclo em 10s...")
            sleep(10)

# =============================================================
# 🚀 EXECUÇÃO PRINCIPAL
# =============================================================
if __name__ == "__main__":
    run_diagnostics()
    
    if not EMAIL or not PASSWORD:
        print("⛔ Configure EMAIL e PASSWORD nas Variáveis de Ambiente!")
    else:
        init_firebase()
        threads = []
        
        # Mostra quantos bots estão ativos
        print(f"🚀 Iniciando {len(CONFIG_BOTS)} Bots com LARGADA ESCALONADA...")
        
        for i, cfg in enumerate(CONFIG_BOTS):
            t = threading.Thread(target=run_bot_thread, args=(cfg,))
            t.start()
            threads.append(t)
            
            # Só aguarda se tiver mais bots na fila
            if i < len(CONFIG_BOTS) - 1:
                print(f"⏳ Aguardando 40s para iniciar o próximo bot...")
                sleep(40)
            
        for t in threads:
            t.join()
        
