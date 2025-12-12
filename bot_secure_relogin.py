from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from time import sleep, time
from datetime import datetime
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, NoSuchElementException
import firebase_admin
from firebase_admin import credentials, db
import os
import pytz
import logging
import threading
import sys
import subprocess
import traceback
import gc  # Importante para limpar memória RAM

# =============================================================
# ⚠️ CONTROLE GLOBAL DE THREADS E DRIVER
# =============================================================
DRIVER_LOCK = threading.Lock() 
STOP_EVENT = threading.Event() 

# =============================================================
# 🔥 GOATHBOT V6.2 - SUPER LIGHT (OTIMIZADO)
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

# =============================================================
# ⚡ CONFIGURAÇÕES DE PERFORMANCE
# =============================================================
# Aumentado para 1.0s para reduzir drasticamente o uso de CPU.
# O jogo demora >5s entre rodadas, então 1s é seguro.
POLLING_INTERVAL = 1.0          
TEMPO_MAX_INATIVIDADE = 600     # 10 minutos sem novos dados
CICLO_MAXIMO_SEGUNDOS = 1800    # 30 minutos: Reinicia o navegador para limpar RAM acumulada

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
    sys.exit()

def getColorClass(value):
    try:
        m = float(value)
        if 1.0 <= m < 2.0: return "blue-bg"
        if 2.0 <= m < 10.0: return "purple-bg"
        if m >= 10.0: return "magenta-bg"
        return "default-bg"
    except: return "default-bg"

def enviar_firebase_async(path, data, nome_jogo):
    """Envia dados ao Firebase em uma thread separada"""
    def _send():
        try:
            key = datetime.now(TZ_BR).strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '')
            db.reference(f"{path}/{key}").set(data)
            print(f"🔥 [{nome_jogo.upper()}] {data['multiplier']}x às {data['time']}")
        except Exception:
            pass 
    threading.Thread(target=_send).start()

def verificar_modais_bloqueio(driver):
    """Fecha popups chatos"""
    xpaths = [
        "//button[contains(., 'Sim')]", 
        "//button[@data-age-action='yes']", 
        "//div[contains(text(), '18')]/following::button[1]",
        "//button[contains(., 'Aceitar')]",
        "//button[contains(., 'Fechar')]" 
    ]
    for xp in xpaths:
        try:
            btn = driver.find_element(By.XPATH, xp)
            if btn.is_displayed(): 
                driver.execute_script("arguments[0].click();", btn)
                sleep(0.5)
        except: pass

# =============================================================
# 🛠️ DRIVER E NAVEGAÇÃO (OTIMIZADO PARA RAM)
# =============================================================
def initialize_driver_instance():
    # 1. Limpeza de processos zumbis antes de começar
    try:
        if os.name == 'nt': # Windows
            subprocess.run("taskkill /f /im chromedriver.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            subprocess.run("taskkill /f /im chrome.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        else: # Linux (Square Cloud)
            os.system("pkill -9 chrome")
            os.system("pkill -9 chromedriver")
    except: pass

    options = webdriver.ChromeOptions()
    options.page_load_strategy = 'eager'
    options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage") # Vital para containers
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--window-size=1280,720") # Resolução menor gasta menos RAM
    options.add_argument("--disable-gpu") # Desativa GPU (economiza RAM em headless)
    options.add_argument("--disable-extensions")
    options.add_argument("--dns-prefetch-disable")
    
    # 2. BLOQUEIO DE IMAGENS, CSS E FONTES (GRANDE ECONOMIA DE RAM)
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheets": 2, 
        "profile.managed_default_content_settings.fonts": 2,
        "profile.default_content_setting_values.notifications": 2,
        "profile.default_content_settings.popups": 0
    }
    options.add_experimental_option("prefs", prefs)

    options.add_argument("--log-level=3")
    options.add_argument("--silent")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
    
    try:
        # Tenta caminho Linux padrão
        return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)
    except:
        # Fallback (Windows/Local)
        # return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        return webdriver.Chrome(options=options)


def setup_tabs_and_login(driver):
    print("➡️ Acessando site (Modo Econômico)...")
    
    try:
        driver.get(URL_DO_SITE)
        sleep(3)
        verificar_modais_bloqueio(driver)

        btns = driver.find_elements(By.XPATH, "//button[contains(., 'Entrar')] | //a[contains(@href, 'login')]") 
        if btns: 
            driver.execute_script("arguments[0].click();", btns[0])
            sleep(1)
            
        driver.find_element(By.NAME, "email").send_keys(EMAIL)
        driver.find_element(By.NAME, "password").send_keys(PASSWORD)
        sleep(0.5)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        print("✅ Login enviado.")
        sleep(5) 
    except Exception as e:
        print(f"⚠️ Aviso no login: {e}")

    handles = {}
    
    # Aba 1
    config1 = CONFIG_BOTS[0]
    driver.get(config1["link"])
    sleep(3) # Reduzi o tempo de espera pois não carrega imagens
    handles[config1["firebase_path"]] = driver.current_window_handle
    print(f"✅ Aba {config1['nome']} pronta.")

    # Aba 2
    config2 = CONFIG_BOTS[1]
    driver.execute_script("window.open('');")
    new_handle = [h for h in driver.window_handles if h != driver.current_window_handle][0]
    driver.switch_to.window(new_handle)
    driver.get(config2["link"])
    sleep(3)
    handles[config2["firebase_path"]] = driver.current_window_handle
    print(f"✅ Aba {config2['nome']} pronta.")
    
    driver.switch_to.window(handles[config1["firebase_path"]]) 
    return handles

# =============================================================
# 🎮 BUSCA DE ELEMENTOS
# =============================================================
def find_game_elements(driver, game_handle):
    try:
        driver.switch_to.window(game_handle)
        driver.switch_to.default_content()
        
        iframe = WebDriverWait(driver, 10).until( 
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'))
        )
        driver.switch_to.frame(iframe)
        
        hist = WebDriverWait(driver, 5).until( 
            EC.presence_of_element_located((By.CSS_SELECTOR, "app-stats-widget, .payouts-block, .payouts-block__list"))
        )
        return iframe, hist
    except:
        return None, None

# =============================================================
# 🔄 THREAD INDIVIDUAL
# =============================================================
def start_bot_thread(driver, bot_config: dict, game_handle: str):
    nome_log = bot_config['nome']
    firebase_path = bot_config['firebase_path']
    
    # Busca inicial
    iframe, hist_element = find_game_elements(driver, game_handle)
    
    LAST_SENT = None
    ULTIMO_MULTIPLIER_TIME = time()
    
    while not STOP_EVENT.is_set():
        raw_text = None
        
        # === SEÇÃO CRÍTICA ===
        with DRIVER_LOCK:
            if STOP_EVENT.is_set(): break
            try:
                driver.switch_to.window(game_handle)
                
                if not iframe or not hist_element:
                    iframe, hist_element = find_game_elements(driver, game_handle)
                    if not iframe: raise Exception("Recarregando elementos...")

                try: driver.switch_to.frame(iframe)
                except: pass

                first_payout = hist_element.find_element(By.CSS_SELECTOR, ".payout:first-child, .bubble-multiplier:first-child")
                raw_text = first_payout.get_attribute("innerText")
                
            except Exception:
                iframe = None 
                hist_element = None
                continue 
        # === FIM CRÍTICA ===
        
        if raw_text:
            clean_text = raw_text.strip().lower().replace('x', '').replace(',', '.')
            if clean_text:
                try:
                    novo_valor = float(clean_text)
                    if novo_valor != LAST_SENT:
                        now_br = datetime.now(TZ_BR)
                        payload = {
                            "multiplier": f"{novo_valor:.2f}",
                            "time": now_br.strftime("%H:%M:%S"),
                            "color": getColorClass(novo_valor),
                            "date": now_br.strftime("%Y-%m-%d")
                        }
                        enviar_firebase_async(firebase_path, payload, nome_log)
                        LAST_SENT = novo_valor
                        ULTIMO_MULTIPLIER_TIME = time()
                except: pass 

        # Checagem de Inatividade
        if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
            print(f"🚨 {nome_log}: Sem dados há {TEMPO_MAX_INATIVIDADE}s. Reiniciando...")
            STOP_EVENT.set() 
            return 
        
        sleep(POLLING_INTERVAL)

# =============================================================
# 🚀 SUPERVISOR (MAIN LOOP)
# =============================================================
def rodar_ciclo_monitoramento():
    DRIVER = None
    STOP_EVENT.clear() 
    inicio_ciclo = time()
    
    try:
        print("\n🔵 INICIANDO NOVO CICLO...")
        DRIVER = initialize_driver_instance()
        handles = setup_tabs_and_login(DRIVER)
        
        threads = []
        for config in CONFIG_BOTS:
            path = config["firebase_path"]
            handle = handles.get(path)
            if handle:
                t = threading.Thread(target=start_bot_thread, args=(DRIVER, config, handle))
                t.start()
                threads.append(t)

        print("⏳ Monitoramento rodando...")
        
        # Loop principal do Supervisor
        while any(t.is_alive() for t in threads):
            if STOP_EVENT.is_set():
                break
            
            # REINÍCIO PREVENTIVO (Limpa RAM acumulada)
            tempo_rodando = time() - inicio_ciclo
            if tempo_rodando > CICLO_MAXIMO_SEGUNDOS:
                print(f"♻️ Ciclo de {CICLO_MAXIMO_SEGUNDOS}s atingido. Reiniciando para limpeza de RAM...")
                STOP_EVENT.set()
                break
                
            sleep(2)
            
    except Exception as e:
        print(f"\n❌ ERRO NO CICLO: {e}")
        traceback.print_exc()
    finally:
        print("🛑 Encerrando ciclo...")
        STOP_EVENT.set() 
        
        # Aguarda threads
        for t in threads:
            if t.is_alive(): t.join(timeout=2) 

        # Fecha driver
        if DRIVER:
            try:
                DRIVER.quit()
                print("🗑️ Driver fechado.")
            except: pass
        
        # 🔥 O PULO DO GATO: LIMPEZA FORÇADA DE RAM
        DRIVER = None
        gc.collect() 
        print("🧹 Memória RAM liberada (GC).")
        sleep(3) 

if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD.")
        sys.exit()
    
    print("==============================================")
    print("   GOATHBOT V6.2 - OTIMIZADO (RAM SAVER)      ")
    print("==============================================")

    while True:
        try:
            rodar_ciclo_monitoramento()
            print("💤 Aguardando 5s para novo ciclo...\n")
            sleep(5)
        except KeyboardInterrupt:
            print("\n🚫 Parada manual.")
            break
        except Exception as e:
            print(f"❌ Erro crítico Supervisor: {e}")
            sleep(10)
