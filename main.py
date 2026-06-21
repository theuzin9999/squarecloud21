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

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

from undetected_chromedriver import ChromeOptions
import undetected_chromedriver as uc
from selenium_stealth import stealth

import firebase_admin
from firebase_admin import credentials, db

# =============================================================
# ⚠️ CONTROLE GLOBAL
# =============================================================
STOP_EVENT = threading.Event() 
DRIVER_LOCK = threading.Lock()

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
URL_DO_SITE = "https://www.goathbet.com"
LINK_AVIATOR_ORIGINAL = "https://www.goathbet.com/pt/casino/spribe/aviator"
LINK_AVIATOR_2 = "https://www.goathbet.bet/casino/spribe/aviator-vip"

FIREBASE_PATH_ORIGINAL = "history"
FIREBASE_PATH_2 = "aviator2"

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

POLLING_INTERVAL = 1.0
TEMPO_MAX_INATIVIDADE = 360
TZ_BR = pytz.timezone("America/Sao_Paulo")
HORA_REINICIO = 23
MINUTO_REINICIO = 59

# =============================================================
# 🔧 FUNÇÕES AUXILIARES E TRATAMENTO DE MODAIS
# =============================================================
def run_diagnostics():
    print("\n--- 🕵️ DIAGNÓSTICO DE CONEXÃO ---")
    try:
        ip = requests.get('https://api.ipify.org', timeout=10).text
        print(f"🌐 IP Público: {ip}")
        res = requests.get(URL_DO_SITE, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        print(f"📡 Status Site (Requests normal): {res.status_code}")
    except Exception as e:
        print(f"⚠️ Alerta de Rede: {e}")
    print("----------------------------------\n")

def limpar_pngs_antigos():
    """🧹 Remove todos os prints da raiz a cada reinício para economizar espaço"""
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
            if nome_jogo == "HISTORY":
                nome_jogo = "AVIATOR 1"
            print(f"🔥 {nome_jogo}: {data['multiplier']}x às {data['time']}")
        except Exception:
            pass 
    threading.Thread(target=_send, daemon=True).start()

def verificar_modais_bloqueio(driver):
    """Fecha ativamente modais conhecidos e o aviso de cookies na página externa"""
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

def checar_e_aceitar_cookies_iframe(driver, estado_cookies):
    """
    Detecta e limpa o banner de cookies específico da Spribe que nasce dentro de cada iframe.
    Usa uma trava local para clicar apenas uma vez e não entrar em loop.
    """
    if estado_cookies.get('aceito', False):
        return

    try:
        btn_cookies_interno = None
        xpaths_tentativas = [
            "//button[contains(text(), 'ACEITAR TODOS') or contains(., 'ACEITAR TODOS')]",
            "//button[contains(@class, 'success') or contains(@class, 'green')]",
            "//button[./span[contains(text(), 'ACEITAR TODOS')]]"
        ]
        
        for xpath in xpaths_tentativas:
            try:
                elemento = driver.find_element(By.XPATH, xpath)
                if elemento.is_displayed() and elemento.size['width'] > 0:
                    btn_cookies_interno = elemento
                    break
            except:
                continue

        if btn_cookies_interno:
            driver.execute_script("arguments[0].click();", btn_cookies_interno)
            print("🛡️ [Iframe] Banner de cookies interno limpo com sucesso!")
            estado_cookies['aceito'] = True
            sleep(2)
    except:
        pass

def stealth_script_inject(driver):
    """Injeta script adicional para mascarar o Selenium"""
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
# 🚀 DRIVER COM UNDETECTED-CHROMEDRIVER
# =============================================================
def initialize_driver_instance():
    try:
        if os.name == 'nt': 
            subprocess.run("taskkill /f /im chromedriver.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            subprocess.run("taskkill /f /im chrome.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        else:
            subprocess.run("killall -9 chromium-browser chromium chromedriver 2>/dev/null", shell=True)
    except: pass

    options = ChromeOptions()
    options.page_load_strategy = 'eager'
    
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-popup-blocking")
    
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")

    try:
        driver = uc.Chrome(options=options, version_main=148)
        
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
        print(f"⚠️ Erro ao instalar/iniciar driver: {e}")
        return None

def setup_navegador_unico(driver, url_jogo, nome_jogo):
    """
    Faz login uma vez no site principal e abre um navegador separado para o jogo especificado.
    Retorna o driver pronto ou None em caso de falha.
    """
    print(f"➡️ Configurando {nome_jogo} em navegador dedicado...")
    try:
        driver.get(URL_DO_SITE)
        sleep(12)
        
        verificar_modais_bloqueio(driver)

        botao_entrar = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Entrar')] | //a[contains(., 'Entrar')] | //*[text()='Entrar']"))
        )
        
        driver.execute_script("arguments[0].click();", botao_entrar)
        print(f"👉 [{nome_jogo}] Botão 'Entrar' clicado via JS.")
        sleep(4)
        
        input_email = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.XPATH, "//input[@id='email' or @name='email']"))
        )
        input_email.send_keys(EMAIL)
        
        input_pass = driver.find_element(By.XPATH, "//input[@id='password' or @name='password']")
        input_pass.send_keys(PASSWORD)
        
        botao_submit = driver.find_element(By.XPATH, "//button[@type='submit']")
        driver.execute_script("arguments[0].click();", botao_submit)
        
        print(f"✅ [{nome_jogo}] Formulário de login enviado.")
        sleep(12)
        
        driver.get(url_jogo)
        sleep(12)
        
        for retry in range(3):
            if driver.find_elements(By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'):
                break
            print(f"⏳ [{nome_jogo}] Aguardando iframe... (tentativa {retry+1}/3)")
            sleep(5)
        
        print(f"✅ [{nome_jogo}] Navegador dedicado configurado.")
        return driver
        
    except Exception as e:
        print(f"❌ ERRO CRÍTICO NAS ETAPAS DE LOGIN/ABERTURA [{nome_jogo}]: {e}")
        try:
            driver.save_screenshot(f"erro_login_{nome_jogo.replace(' ', '_')}.png")
        except: pass
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
# 🔄 LOOP DE CAPTURA COM SUPORTE ANTIBLOCK COOKIES
# =============================================================
def start_bot(driver, firebase_path, nome_jogo):
    print(f"🚀 [{nome_jogo}] Monitorando '{firebase_path}'...")
    
    LAST_SENT = None
    ULTIMO_MULTIPLIER_TIME = time()
    data_atual = datetime.now(TZ_BR).date()
    estado_cookies = {'aceito': False}
    primeira_execucao = True

    while not STOP_EVENT.is_set():
        now_br = datetime.now(TZ_BR)
        if (now_br.hour == HORA_REINICIO and now_br.minute >= MINUTO_REINICIO) or (now_br.hour == 0 and now_br.minute <= 5 and now_br.date() != data_atual):
            print(f"🌙 [{nome_jogo}] Reinício diário ({HORA_REINICIO}:{MINUTO_REINICIO:02d})...")
            return
        
        raw_text = None
        with DRIVER_LOCK:
            if STOP_EVENT.is_set(): break
            try:
                driver.switch_to.window(driver.current_window_handle)
                driver.switch_to.default_content()
                iframe, hist_element = find_game_elements_safe(driver)
                
                if iframe:
                    checar_e_aceitar_cookies_iframe(driver, estado_cookies)
                
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
                    if primeiro_valor or novo_valor != LAST_SENT:
                        payload = {
                            "multiplier": f"{novo_valor:.2f}",
                            "time": now_br.strftime("%H:%M:%S"),
                            "color": getColorClass(novo_valor),
                            "date": now_br.strftime("%Y-%m-%d")
                        }
                        key = now_br.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                        enviar_firebase_async(f"{firebase_path}/{key}", payload)
                        print(f"🔥 [{nome_jogo}] {payload['multiplier']}x")
                        LAST_SENT = novo_valor
                        ULTIMO_MULTIPLIER_TIME = time()
                        primeiro_valor = False
                except: pass
        else:
            primeiro_valor = True

        if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
            print(f"⚠️ [{nome_jogo}] Sem dados por {TEMPO_MAX_INATIVIDADE}s. Reiniciando...")
            return
            
        sleep(POLLING_INTERVAL + 0.5)

# =============================================================
# 🚀 SUPERVISOR DEDICADO POR NAVEGADOR
# =============================================================
def supervisor_navegador(driver, firebase_path, nome_jogo):
    """Gerencia ciclo completo de um navegador dedicado"""
    try:
        start_bot(driver, firebase_path, nome_jogo)
    except Exception as e:
        print(f"❌ [{nome_jogo}] Erro no supervisor: {e}")
    finally:
        try:
            driver.quit()
            print(f"🗑️ [{nome_jogo}] Driver encerrado.")
        except: pass

def rodar_ciclo_monitoramento():
    limpar_pngs_antigos()
    
    driver1 = None
    driver2 = None
    
    try:
        print("\n🔵 INICIANDO NAVEGADOR 1 - AVIATOR 1...")
        driver1 = initialize_driver_instance()
        if not driver1:
            print("⚠️ Falha ao instanciar driver 1.")
            return
        
        resultado1 = setup_navegador_unico(driver1, LINK_AVIATOR_ORIGINAL, "Aviator 1")
        if not resultado1:
            print("⚠️ Falha ao configurar Aviator 1.")
            if driver1:
                driver1.quit()
            return
        driver1 = resultado1
        
        print("\n🔵 INICIANDO NAVEGADOR 2 - AVIATOR 2 (VIP)...")
        driver2 = initialize_driver_instance()
        if not driver2:
            print("⚠️ Falha ao instanciar driver 2.")
            if driver1:
                driver1.quit()
            return
        
        resultado2 = setup_navegador_unico(driver2, LINK_AVIATOR_2, "Aviator 2")
        if not resultado2:
            print("⚠️ Falha ao configurar Aviator 2.")
            if driver1:
                driver1.quit()
            if driver2:
                driver2.quit()
            return
        driver2 = resultado2
        
        print("\n⏳ Monitoramento iniciado (2 Navegadores Dedicados)...")
        
        t1 = threading.Thread(target=supervisor_navegador, args=(driver1, FIREBASE_PATH_ORIGINAL, "Aviator 1"), daemon=True)
        t2 = threading.Thread(target=supervisor_navegador, args=(driver2, FIREBASE_PATH_2, "Aviator 2"), daemon=True)

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
        if driver1:
            try:
                driver1.quit()
                print("🗑️ Driver 1 encerrado.")
            except: pass
        if driver2:
            try:
                driver2.quit()
                print("🗑️ Driver 2 encerrado.")
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
