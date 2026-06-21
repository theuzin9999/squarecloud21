import os
import sys
import pytz
import logging
import threading
import gc
import requests
import subprocess
import traceback
import glob
from time import sleep, time
from datetime import datetime

# 🔥 SELENIUM PADRÃO E CONFIGURAÇÕES DE SERVIÇO
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# 🛡️ BIBLIOTECA DE OCULTAÇÃO DE AUTOMAÇÃO
from selenium_stealth import stealth

import firebase_admin
from firebase_admin import credentials, db

# =============================================================
# ⚠️ CONTROLE GLOBAL DE THREADS E DRIVER
# =============================================================
DRIVER_LOCK = threading.Lock() 
STOP_EVENT = threading.Event() 

# =============================================================
# 🔥 CONFIGURAÇÃO FIREBASE
# =============================================================
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'

try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
    print("✅ Firebase Admin SDK inicializado.")
except Exception as e:
    print(f"\n❌ ERRO CONEXÃO FIREBASE: {e}")
    sys.exit()

# =============================================================
# ⚙️ VARIÁVEIS OFICIAIS GOATHBET
# =============================================================
URL_DO_SITE = "https://www.goathbet.bet"
LINK_AVIATOR_ORIGINAL = "https://www.goathbet.bet/pt/casino/spribe/aviator"
LINK_AVIATOR_2 = "https://www.goathbet.bet/casino/spribe/aviator-vip"

FIREBASE_PATH_ORIGINAL = "history"
FIREBASE_PATH_2 = "aviator2"

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

POLLING_INTERVAL = 1.0       
TEMPO_MAX_INATIVIDADE = 360 
TZ_BR = pytz.timezone("America/Sao_Paulo")

# =============================================================
# 🔧 FUNÇÕES AUXILIARES E TRATAMENTO DE MODAIS
# =============================================================
def run_diagnostics():
    print("\n--- 🕵️ DIAGNÓSTICO DE CONEXÃO ---")
    try:
        ip = requests.get('https://api.ipify.org', timeout=10).text
        print(f"🌐 IP Público da Hospedagem: {ip}")
    except Exception as e:
        print(f"⚠️ Alerta de Rede: {e}")
    print("----------------------------------\n")

def limpar_pngs_antigos():
    try:
        arquivos_png = glob.glob("*.png")
        if arquivos_png:
            for f in arquivos_png:
                os.remove(f)
            print(f"🧹 Limpeza concluída: {len(arquivos_png)} prints residuais deletados.")
        else:
            print("🧹 Limpeza concluída: Nenhum print antigo encontrado.")
    except Exception as e:
        print(f"⚠️ Erro ao limpar imagens antigas: {e}")

def getColorClass(value):
    try:
        m = float(value)
        if 1.0 <= m < 2.0: return "blue-bg"
        if 2.0 <= m < 10.0: return "purple-bg"
        if m >= 10.0: return "magenta-bg"
        return "default-bg"
    except: return "default-bg"

def enviar_firebase_async(path, data):
    def _send():
        try:
            db.reference(path).set(data)
            nome_jogo = path.split('/')[0].upper()
            if nome_jogo == "HISTORY": nome_jogo = "AVIATOR 1"
            print(f"🔥 {nome_jogo}: {data['multiplier']}x às {data['time']}")
        except Exception:
            pass 
    threading.Thread(target=_send, daemon=True).start()

def verificar_modais_bloqueio(driver):
    try:
        btn_cookies = driver.find_element(By.XPATH, "//button[contains(text(), 'ACEITAR TODOS') or contains(., 'ACEITAR TODOS')]")
        driver.execute_script("arguments[0].click();", btn_cookies)
        print("✅ Banner de Cookies geral aceito.")
        sleep(1)
    except: pass

    try:
        btn_18 = driver.find_element(By.XPATH, "//span[contains(text(), 'Sim, sou maior de 18')] | //button[contains(., 'Sim, sou maior de 18')]")
        driver.execute_script("arguments[0].click();", btn_18)
        sleep(1)
        print("✅ Modal 'Maior de 18' fechado.")
    except: pass

    try:
        btn_fechar_cadastro = driver.find_element(By.XPATH, "//button[@data-slot='dialog-close'] | //button[contains(@class, 'modal-close')]")
        driver.execute_script("arguments[0].click();", btn_fechar_cadastro)
        sleep(1)
        print("✅ Modal 'Novo Cadastro' ocultado.")
    except: pass

def stealth_script_inject(driver):
    stealth_js = """
    Object.defineProperty(navigator, 'webdriver', {
      get: () => false,
    });
    """
    try:
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': stealth_js
        })
    except Exception as e:
        print(f"Aviso ao injetar stealth script: {e}")

# =============================================================
# 🚀 DRIVER COM SELENIUM PADRÃO + ANTIBOT FLAGS
# =============================================================
def initialize_driver_instance():
    try:
        if os.name == 'nt': 
            subprocess.run("taskkill /f /im chromedriver.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            subprocess.run("taskkill /f /im chrome.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        else:
            subprocess.run("killall -9 chromium-browser chromium chromedriver 2>/dev/null", shell=True)
    except: pass

    options = webdriver.ChromeOptions()
    options.page_load_strategy = 'eager'
    
    # Flags de performance e Headless estável para Linux/Square Cloud
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--window-size=1920,1080")
    
    # Forçar User-Agent real e remover traços de automação nativamente
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    try:
        # Gerencia e instala automaticamente a versão correta do Chromedriver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # Aplica a camuflagem stealth por cima do driver padrão
        stealth(driver,
            languages=["pt-BR", "pt"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )
        return driver
    except Exception as e:
        print(f"⚠️ Erro ao instalar/iniciar driver padrão: {e}")
        return None

def setup_tabs(driver):
    stealth_script_inject(driver)
    
    print("➡️ Acessando site e configurando abas para economizar RAM...")
    try:
        driver.get(URL_DO_SITE)
        sleep(12) 
        
        verificar_modais_bloqueio(driver)

        botao_entrar = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Entrar')] | //a[contains(., 'Entrar')] | //*[text()='Entrar']"))
        )
        
        driver.execute_script("arguments[0].click();", botao_entrar)
        print("👉 Botão 'Entrar' clicado via JS com sucesso.")
        sleep(4)
        
        input_email = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.XPATH, "//input[@id='email' or @name='email']"))
        )
        input_email.send_keys(EMAIL)
        
        input_pass = driver.find_element(By.XPATH, "//input[@id='password' or @name='password']")
        input_pass.send_keys(PASSWORD)
        
        botao_submit = driver.find_element(By.XPATH, "//button[@type='submit']")
        driver.execute_script("arguments[0].click();", botao_submit)
        
        print("✅ Formulário de login enviado.")
        sleep(12) 
    except Exception as e:
        print(f"❌ ERRO CRÍTICO NAS ETAPAS DE LOGIN: {e}")
        try: driver.save_screenshot("erro_login.png")
        except: pass
        return None

    # =============================================================
    # 🔄 DIRECIONAMENTO E LIMPEZA DE COOKIES NAS ABAS DOS JOGOS
    # =============================================================
    try:
        print("🎯 Configurando Aviator 1 (Aba Principal)...")
        try:
            card_aviator1 = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((By.XPATH, "//img[@alt='Aviator']"))
            )
            card_aviator1.click()
        except Exception:
            print("⚠️ Falha ao clicar no card. Navegando diretamente...")
            driver.get(LINK_AVIATOR_ORIGINAL)
            
        sleep(12) 
        handle_original = driver.current_window_handle

        # [COOKIES APÓS LOGIN - AVIATOR 1]
        try:
            if driver.find_elements(By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'):
                iframe = driver.find_element(By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]')
                driver.switch_to.frame(iframe)
                for xpath in ["//button[contains(text(), 'ACEITAR TODOS')]", "//button[contains(., 'ACEITAR TODOS')]", "//button[contains(@class, 'success')]"]:
                    try:
                        driver.find_element(By.XPATH, xpath).click()
                        print("🛡️ [Aviator 1] Banner de cookies limpo com sucesso após login!")
                        break
                    except: pass
                driver.switch_to.default_content()
        except: pass

        # [📸 PRINT SELEÇÃO AVIATOR 1]
        try:
            driver.save_screenshot("aviator1_aberto.png")
            print("📸 [Print] Imagem 'aviator1_aberto.png' salva com sucesso.")
        except Exception as e:
            print(f"⚠️ Falha ao gerar print do Aviator 1: {e}")

        print(f"✅ Aba Aviator 1 configurada.")

        print("🎯 Configurando Aviator 2 VIP (Nova Aba)...")
        driver.execute_script("window.open('');")
        sleep(2)
        handles = driver.window_handles
        handle_aviator2 = handles[-1] # Garante foco na aba recém-criada
        
        driver.switch_to.window(handle_aviator2)
        driver.get(LINK_AVIATOR_2)
        sleep(12)
        
        for retry in range(3):
            if driver.find_elements(By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'):
                break
            print(f"⏳ Aguardando iframe Aviator 2... (tentativa {retry+1}/3)")
            sleep(5)
            
        # [COOKIES APÓS LOGIN - AVIATOR 2]
        try:
            if driver.find_elements(By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'):
                iframe = driver.find_element(By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]')
                driver.switch_to.frame(iframe)
                for xpath in ["//button[contains(text(), 'ACEITAR TODOS')]", "//button[contains(., 'ACEITAR TODOS')]", "//button[contains(@class, 'success')]"]:
                    try:
                        driver.find_element(By.XPATH, xpath).click()
                        print("🛡️ [Aviator 2] Banner de cookies limpo com sucesso após login!")
                        break
                    except: pass
                driver.switch_to.default_content()
        except: pass

        # [📸 PRINT SELEÇÃO AVIATOR 2]
        try:
            driver.save_screenshot("aviator2_aberto.png")
            print("📸 [Print] Imagem 'aviator2_aberto.png' salva com sucesso.")
        except Exception as e:
            print(f"⚠️ Falha ao gerar print do Aviator 2: {e}")
        
        print(f"✅ Aba Aviator 2 configurada.")
        driver.switch_to.window(handle_original)
        return {FIREBASE_PATH_ORIGINAL: handle_original, FIREBASE_PATH_2: handle_aviator2}
        
    except Exception as e:
        print(f"⚠️ Falha fatal ao estruturar as páginas internas do jogo: {e}")
        return None

# =============================================================
# 🎮 BUSCA DE ELEMENTOS
# =============================================================
def find_game_elements_safe(driver):
    try:
        driver.implicitly_wait(2)
        iframe = driver.find_element(By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]')
        driver.switch_to.frame(iframe)
        hist = driver.find_element(By.CSS_SELECTOR, ".payouts-block, app-stats-widget")
        driver.implicitly_wait(10)
        return iframe, hist
    except Exception as e:
        driver.implicitly_wait(10)
        return None, None

# =============================================================
# 🔄 LOOP DE CAPTURA LIMPO
# =============================================================
def start_bot(driver, game_handle, firebase_path):
    nome_log = "AVIATOR 1" if "history" in firebase_path else "AVIATOR 2"
    print(f"🚀 [{nome_log}] Monitorando '{firebase_path}'...")
    
    LAST_SENT = None
    ULTIMO_MULTIPLIER_TIME = time()

    while not STOP_EVENT.is_set():
        now_br = datetime.now(TZ_BR)
        
        if now_br.hour == 23 and now_br.minute == 59:
            print(f"🌙 [{nome_log}] Reinício diário agendado (23:59)...")
            STOP_EVENT.set()
            return
        
        raw_text = None
        with DRIVER_LOCK:
            if STOP_EVENT.is_set(): break
            try:
                driver.switch_to.window(game_handle)
                driver.switch_to.default_content()
                iframe, hist_element = find_game_elements_safe(driver)
                
                if hist_element:
                    first_payout = hist_element.find_element(
                        By.CSS_SELECTOR, ".payout:first-child, .bubble-multiplier:first-child"
                    )
                    raw_text = first_payout.get_attribute("innerText")
            except Exception as e:
                pass
        
        if raw_text:
            clean_text = raw_text.strip().lower().replace('x', '').replace('\n', '').strip()
            if clean_text:
                try:
                    novo_valor = float(clean_text)
                    if novo_valor != LAST_SENT:
                        payload = {
                            "multiplier": f"{novo_valor:.2f}",
                            "time": now_br.strftime("%H:%M:%S"),
                            "color": getColorClass(novo_valor),
                            "date": now_br.strftime("%Y-%m-%d")
                        }
                        
                        key = now_br.strftime("%Y-%m-%d_%H-%M-%S-%f")
                        enviar_firebase_async(f"{firebase_path}/{key}", payload)
                        LAST_SENT = novo_valor
                        ULTIMO_MULTIPLIER_TIME = time()
                except: pass

        if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
            print(f"⚠️ [{nome_log}] Sem dados por {TEMPO_MAX_INATIVIDADE}s. Reiniciando...")
            STOP_EVENT.set()
            return
            
        sleep(POLLING_INTERVAL + 0.5)

# =============================================================
# 🚀 SUPERVISOR (MAIN LOOP)
# =============================================================
def rodar_ciclo_monitoramento():
    DRIVER = None
    STOP_EVENT.clear() 
    
    limpar_pngs_antigos()
    
    try:
        print("\n🔵 INICIANDO NOVO CICLO COM CHROMEDRIVER PADRÃO + STEALTH...")
        DRIVER = initialize_driver_instance()
        
        if not DRIVER:
            print("⚠️ Falha ao instanciar o driver. Aguardando para nova tentativa...")
            sleep(10)
            return

        handles = setup_tabs(DRIVER)
        
        if not handles:
            print("⚠️ Ciclo interrompido por falhas de carregamento. Reiniciando driver...")
            return

        handle_original = handles[FIREBASE_PATH_ORIGINAL]
        handle_aviator2 = handles[FIREBASE_PATH_2]

        print("⏳ Monitoramento iniciado (Threads)...")
        
        t1 = threading.Thread(target=start_bot, args=(DRIVER, handle_original, FIREBASE_PATH_ORIGINAL), daemon=True)
        t2 = threading.Thread(target=start_bot, args=(DRIVER, handle_aviator2, FIREBASE_PATH_2), daemon=True)

        t1.start()
        t2.start()

        while t1.is_alive() or t2.is_alive():
            if STOP_EVENT.is_set():
                break
            sleep(2)
            
        print("🛑 Ciclo encerrado. Limpando recursos...")
        
    except Exception as e:
        print(f"\n❌ ERRO NO CICLO: {e}")
        traceback.print_exc()
    finally:
        STOP_EVENT.set() 
        if DRIVER:
            try:
                DRIVER.quit()
                print("🗑️ Driver encerrado com sucesso.")
            except: pass
        gc.collect()
        sleep(5) 

if __name__ == "__main__":
    run_diagnostics()
    
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD nas variáveis de ambiente.")
        sys.exit()
    
    print("==============================================")
    print("     SUPERVISOR DE BOT INICIADO (24H)        ")
    print("==============================================")

    while True:
        try:
            rodar_ciclo_monitoramento()
            print("♻️ Reiniciando processo em 5 segundos...\n")
            sleep(5)
        except KeyboardInterrupt:
            print("\n🚫 Parada manual pelo usuário.")
            break
        except Exception as e:
            print(f"❌ Erro crítico no Supervisor: {e}")
            sleep(10)
