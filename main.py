import os
import sys
import pytz
import logging
import threading
import gc
import requests
import subprocess
import traceback
import base64
import socket
import json
from time import sleep, time
from datetime import datetime

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

# 🔥 BIBLIOTECAS DE CAMUFLAGEM
import undetected_chromedriver as uc
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
DATABASE_URL = 'https://your-database.firebaseio.com' # Substitua pela sua URL real do Firebase

try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
    print("✅ Firebase Admin SDK inicializado.")
except Exception as e:
    print(f"\n❌ ERRO CONEXÃO FIREBASE: {e}")
    sys.exit()

# =============================================================
# ⚙️ VARIÁVEIS DO SCRIPT
# =============================================================
URL_DO_SITE = "https://www.example.com" # Substitua pelos seus links reais
LINK_AVIATOR_ORIGINAL = "https://www.example.com/pt/casino/spribe/aviator"
LINK_AVIATOR_2 = "https://www.example.com/casino/spribe/aviator-vip"

FIREBASE_PATH_ORIGINAL = "history"
FIREBASE_PATH_2 = "aviator2"

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

POLLING_INTERVAL = 1.0       
TEMPO_MAX_INATIVIDADE = 360 
TZ_BR = pytz.timezone("America/Sao_Paulo")

# =============================================================
# 📡 TUNEL DE PROXY LOCAL NATIVO (WEBSHARE)
# =============================================================
def start_local_proxy_tunnel(local_port, upstream_ip, upstream_port, user, password):
    def tunnel(src, dst):
        try:
            while True:
                data = src.recv(8192)
                if not data:
                    break
                dst.sendall(data)
        except:
            pass
        finally:
            try: src.close()
            except: pass
            try: dst.close()
            except: pass

    def handle_client(client_socket):
        try:
            request = client_socket.recv(4048)
            if not request:
                client_socket.close()
                return

            if request.startswith(b'CONNECT'):
                first_line = request.split(b'\r\n')[0].decode('utf-8', errors='ignore')
                target = first_line.split(' ')[1]

                upstream_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                upstream_socket.connect((upstream_ip, int(upstream_port)))

                auth_str = f"{user}:{password}"
                auth_b64 = base64.b64encode(auth_str.encode()).decode()

                connect_req = f"CONNECT {target} HTTP/1.1\r\nProxy-Authorization: Basic {auth_b64}\r\n\r\n"
                upstream_socket.sendall(connect_req.encode())

                resp = upstream_socket.recv(4048)
                if b"200" in resp or b"Established" in resp:
                    client_socket.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    threading.Thread(target=tunnel, args=(client_socket, upstream_socket), daemon=True).start()
                    threading.Thread(target=tunnel, args=(upstream_socket, client_socket), daemon=True).start()
                else:
                    client_socket.close()
                    upstream_socket.close()
            else:
                upstream_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                upstream_socket.connect((upstream_ip, int(upstream_port)))

                auth_str = f"{user}:{password}"
                auth_b64 = base64.b64encode(auth_str.encode()).decode()

                if b"\r\n\r\n" in request:
                    headers, body = request.split(b"\r\n\r\n", 1)
                    modified_req = headers + f"\r\nProxy-Authorization: Basic {auth_b64}\r\n\r\n".encode() + body
                else:
                    modified_req = request

                upstream_socket.sendall(modified_req)
                threading.Thread(target=tunnel, args=(client_socket, upstream_socket), daemon=True).start()
                threading.Thread(target=tunnel, args=(upstream_socket, client_socket), daemon=True).start()
        except:
            try: client_socket.close()
            except: pass

    def server_loop():
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('127.0.0.1', local_port))
        server.listen(128)
        while True:
            try:
                client_sock, _ = server.accept()
                threading.Thread(target=handle_client, args=(client_sock,), daemon=True).start()
            except:
                break

    t = threading.Thread(target=server_loop, daemon=True)
    t.start()

# =============================================================
# 🔧 FUNÇÕES AUXILIARES
# =============================================================
def check_page_status_code(driver, target_url):
    """
    Inspeciona os logs de performance do Chrome para capturar o
    status code real da resposta HTTP da página principal.
    """
    try:
        logs = driver.get_log('performance')
        for entry in logs:
            log_data = json.loads(entry['message'])['message']
            if log_data['method'] == 'Network.responseReceived':
                response = log_data['params']['response']
                # Verifica se a URL do log bate com o site que estamos acessando
                if target_url in response['url'] or response['url'] == target_url or response['url'] == target_url + "/":
                    return int(response['status'])
    except Exception as e:
        print(f"⚠️ Não foi possível ler os logs de performance: {e}")
    return 200 # Fallback padrão caso não encontre nos logs inicializados

def run_diagnostics():
    print("\n--- 🕵️ DIAGNÓSTICO DE CONEXÃO ---")
    try:
        ip = requests.get('https://api.ipify.org', timeout=10).text
        print(f"🌐 IP Público do Servidor (Sem Proxy): {ip}")
    except Exception as e:
        print(f"⚠️ Alerta de Rede no diagnóstico: {e}")
    print("----------------------------------\n")

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
        btn_18 = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.XPATH, "//span[contains(., 'Sim, sou maior de 18')]"))
        )
        btn_18.click()
        sleep(0.5)
        print("✅ Modal 'Maior de 18' fechado.")
    except: pass

    try:
        xpath_btn_fechar = "//button[@data-slot='dialog-close' and contains(@class, 'modal-close')]"
        btn_fechar_cadastro = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.XPATH, xpath_btn_fechar))
        )
        btn_fechar_cadastro.click()
        sleep(1.5) 
        print("✅ Modal 'Novo Cadastro' fechado.")
    except: pass

    botoes = ["//button[contains(., 'Sim')]", "//button[contains(., 'Aceitar')]", "//button[contains(., 'Fechar')]"]
    for xpath in botoes:
        try:
            btn = driver.find_element(By.XPATH, xpath)
            if btn.is_displayed(): 
                btn.click()
                sleep(0.5)
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
# 🚀 DRIVER COM UNDETECTED-CHROMEDRIVER + TUNEL INTEGRADO
# =============================================================
def initialize_driver_instance():
    try:
        if os.name == 'nt': 
            subprocess.run("taskkill /f /im chromedriver.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            subprocess.run("taskkill /f /im chrome.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        else:
            subprocess.run("killall -9 chromium-browser chromium chromedriver 2>/dev/null", shell=True)
    except: pass

    PROXY_IP = "38.154.203.95"     
    PROXY_PORT = "5863"
    PROXY_USER = "mgczjuye"
    PROXY_PASS = "jdckgvvzq4o1"
    LOCAL_TUNNEL_PORT = 8899

    print(f"📡 Ligando túnel de proxy local na porta {LOCAL_TUNNEL_PORT}...")
    start_local_proxy_tunnel(LOCAL_TUNNEL_PORT, PROXY_IP, PROXY_PORT, PROXY_USER, PROXY_PASS)
    sleep(1.5) 

    options = uc.ChromeOptions()
    options.page_load_strategy = 'eager'
    
    # 📌 ATIVA CAPTURA DE LOGS DE PERFORMANCE (Fundamental para capturar o Status HTTP)
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

    options.add_argument(f"--proxy-server=127.0.0.1:{LOCAL_TUNNEL_PORT}")
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-popup-blocking")
    
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36")
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

def setup_tabs(driver):
    stealth_script_inject(driver)
    
    print("➡️ Acessando site e configurando abas...")
    try:
        driver.get(URL_DO_SITE)
        sleep(5) 

        verificar_modais_bloqueio(driver)

        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Entrar')]"))).click()
        sleep(2)
        driver.find_element(By.NAME, "email").send_keys(EMAIL)
        driver.find_element(By.NAME, "password").send_keys(PASSWORD)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        print("✅ Login enviado.")
        sleep(10) 
    except Exception as e:
        print(f"⚠️ Aviso no login: {e}")

    try:
        driver.get(LINK_AVIATOR_ORIGINAL)
        sleep(5)
        handle_original = driver.current_window_handle
        print(f"✅ Aba Aviator 1 configurada.")

        driver.execute_script("window.open('');")
        handles = driver.window_handles
        handle_aviator2 = [h for h in handles if h != handle_original][0]
        
        driver.switch_to.window(handle_aviator2)
        driver.get(LINK_AVIATOR_2)
        sleep(5)
        print(f"✅ Aba Aviator 2 configurada.")
        
        driver.switch_to.window(handle_original) 
        return {FIREBASE_PATH_ORIGINAL: handle_original, FIREBASE_PATH_2: handle_aviator2}
    except Exception as e:
        print(f"❌ Erro ao configurar abas do jogo: {e}")
        return None

# =============================================================
# 🎮 BUSCA DE ELEMENTOS
# =============================================================
def find_game_elements_safe(driver):
    try:
        driver.implicitly_wait(2)
        iframe = driver.find_element(By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]')
        driver.switch_to.frame(iframe)
        hist = driver.find_element(By.CSS_SELECTOR, "app-stats-widget, .payouts-block")
        driver.implicitly_wait(10)
        return iframe, hist
    except:
        driver.implicitly_wait(10)
        return None, None

# =============================================================
# 🔄 LOOP DE CAPTURA
# =============================================================
def start_bot(driver, game_handle, firebase_path):
    nome_log = "AVIATOR 1" if "history" in firebase_path else "AVIATOR 2"
    print(f"🚀 INICIADO: {nome_log}")
    
    LAST_SENT = None
    ULTIMO_MULTIPLIER_TIME = time()

    while not STOP_EVENT.is_set():
        raw_text = None
        with DRIVER_LOCK:
            if STOP_EVENT.is_set(): break
            try:
                driver.switch_to.window(game_handle)
                driver.switch_to.default_content()
                iframe, hist_element = find_game_elements_safe(driver)
                
                if hist_element:
                    first_payout = hist_element.find_element(
                        By.CSS_SELECTOR, 
                        "[appcoloredmultiplier].payout:first-child, .payout:first-child, .bubble-multiplier:first-child"
                    )
                    raw_text = first_payout.get_attribute("innerText")
            except: pass

        if raw_text:
            clean_text = raw_text.strip().lower().replace('x', '').replace('\n', '').strip()
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
                        chave_firebase = now_br.strftime('%Y-%m-%d_%H-%M-%S-%f')[:-3]
                        enviar_firebase_async(f"{firebase_path}/{chave_firebase}", payload)
                        
                        LAST_SENT = novo_valor
                        ULTIMO_MULTIPLIER_TIME = time()
                except: pass 

        if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
            print(f"⚠️ [{nome_log}] Sem dados por mais de {TEMPO_MAX_INATIVIDADE}s. Reiniciando...")
            STOP_EVENT.set()
            return 
            
        sleep(POLLING_INTERVAL)

# =============================================================
# 🚀 SUPERVISOR (MAIN LOOP)
# =============================================================
def rodar_ciclo_monitoramento():
    DRIVER = None
    STOP_EVENT.clear() 
    
    try:
        print("\n🔵 INICIANDO NOVO CICLO COM PROXY WEBSHARE + UC...")
        DRIVER = initialize_driver_instance()
        
        if not DRIVER:
            print("⚠️ Falha ao instanciar o driver. Aguardando para nova tentativa...")
            sleep(10)
            return

        handles = setup_tabs(DRIVER)
        if not handles:
            print("⚠️ Ciclo interrompido no setup inicial.")
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
        print("❗ Configure EMAIL e PASSWORD nas variáveis de ambiente do painel.")
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
