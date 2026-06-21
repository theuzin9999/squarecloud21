import os
import sys
import pytz
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

import undetected_chromedriver as uc
from selenium_stealth import stealth

import firebase_admin
from firebase_admin import credentials, db

SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'

if not firebase_admin._apps:
    cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
    firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})

URL_DO_SITE = "https://www.goathbet.com"
LINK_AVIATOR = "https://www.goathbet.bet/casino/spribe/aviator-vip"
FIREBASE_PATH = "aviator2"

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

POLLING_INTERVAL = 1.0
TEMPO_MAX_INATIVIDADE = 360
TZ_BR = pytz.timezone("America/Sao_Paulo")
HORA_REINICIO = 23
MINUTO_REINICIO = 59

def run_diagnostics():
    print("\n--- 🕵️ DIAGNÓSTICO DE CONEXÃO ---")
    try:
        ip = requests.get('https://api.ipify.org', timeout=10).text
        res = requests.get(URL_DO_SITE, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        print(f"🌐 IP: {ip} | Status Site: {res.status_code}")
    except Exception as e:
        print(f"⚠️ Alerta de Rede: {e}")
    print("----------------------------------\n")

def limpar_pngs_antigos():
    try:
        arquivos_png = glob.glob("*.png")
        for f in arquivos_png:
            os.remove(f)
        if arquivos_png:
            print(f"🧹 {len(arquivos_png)} prints deletados.")
    except Exception as e:
        print(f"⚠️ Erro ao limpar: {e}")

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
            print(f"🔥 AVIATOR 2: {data['multiplier']}x às {data['time']}")
        except Exception:
            pass
    import threading
    threading.Thread(target=_send, daemon=True).start()

def verificar_modais_bloqueio(driver):
    try:
        btn = driver.find_element(By.XPATH, "//button[contains(text(), 'ACEITAR TODOS') or contains(., 'ACEITAR TODOS')]")
        driver.execute_script("arguments[0].click();", btn)
        print("✅ Cookies geral aceito.")
        sleep(1)
    except: pass
    try:
        btn = driver.find_element(By.XPATH, "//span[contains(text(), 'Sim, sou maior de 18')] | //button[contains(., 'Sim, sou maior de 18')]")
        driver.execute_script("arguments[0].click();", btn)
        print("✅ Modal 18+ fechado.")
        sleep(1)
    except: pass
    try:
        btn = driver.find_element(By.XPATH, "//button[@data-slot='dialog-close'] | //button[contains(@class, 'modal-close')]")
        driver.execute_script("arguments[0].click();", btn)
        print("✅ Modal cadastro ocultado.")
        sleep(1)
    except: pass

def checar_e_aceitar_cookies_iframe(driver, estado_cookies):
    if estado_cookies.get('aceito', False):
        return
    try:
        btn = None
        xpaths = [
            "//button[contains(text(), 'ACEITAR TODOS') or contains(., 'ACEITAR TODOS')]",
            "//button[contains(@class, 'success') or contains(@class, 'green')]",
            "//button[./span[contains(text(), 'ACEITAR TODOS')]]"
        ]
        for xpath in xpaths:
            try:
                el = driver.find_element(By.XPATH, xpath)
                if el.is_displayed() and el.size['width'] > 0:
                    btn = el
                    break
            except:
                continue
        if btn:
            driver.execute_script("arguments[0].click();", btn)
            print("🛡️ [Iframe] Banner de cookies interno limpo com sucesso!")
            estado_cookies['aceito'] = True
            sleep(2)
    except:
        pass

def stealth_script_inject(driver):
    stealth_js = "Object.defineProperty(navigator, 'webdriver', { get: () => false, });"
    try:
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': stealth_js})
    except Exception as e:
        print(f"Aviso stealth: {e}")

def initialize_driver():
    try:
        if os.name == 'nt':
            subprocess.run("taskkill /f /im chromedriver.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            subprocess.run("taskkill /f /im chrome.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        else:
            subprocess.run("killall -9 chromium-browser chromium chromedriver 2>/dev/null", shell=True)
    except: pass
    sleep(2)

    options = uc.ChromeOptions()
    options.page_load_strategy = 'eager'
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")

    try:
        driver = uc.Chrome(options=options, version_main=148, use_subprocess=False)
        stealth(driver,
            languages=["pt-BR", "pt"], vendor="Google Inc.", platform="Win32",
            webgl_vendor="Intel Inc.", renderer="Intel Iris OpenGL Engine", fix_hairline=True)
        return driver
    except Exception as e:
        print(f"⚠️ Erro driver: {e}")
        return None

def setup_navegador(driver):
    nome = "Aviator 2"
    print(f"➡️ Configurando {nome}...")
    try:
        print(f"[{nome}] Acessando site principal...")
        driver.get(URL_DO_SITE)
        sleep(15)
        verificar_modais_bloqueio(driver)

        print(f"[{nome}] Clicando em Entrar...")
        botao_entrar = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Entrar')] | //a[contains(., 'Entrar')] | //*[text()='Entrar']"))
        )
        driver.execute_script("arguments[0].click();", botao_entrar)
        sleep(5)

        print(f"[{nome}] Preenchendo login...")
        input_email = WebDriverWait(driver, 15).until(
            EC.visibility_of_element_located((By.XPATH, "//input[@id='email' or @name='email']"))
        )
        input_email.clear()
        input_email.send_keys(EMAIL)
        input_pass = driver.find_element(By.XPATH, "//input[@id='password' or @name='password']")
        input_pass.clear()
        input_pass.send_keys(PASSWORD)
        botao_submit = driver.find_element(By.XPATH, "//button[@type='submit']")
        driver.execute_script("arguments[0].click();", botao_submit)
        print(f"✅ [{nome}] Login enviado.")
        sleep(15)

        print(f"[{nome}] Acessando jogo VIP...")
        driver.get(LINK_AVIATOR)
        sleep(15)

        print(f"[{nome}] Verificando iframe (5 tentativas)...")
        for i in range(5):
            if driver.find_elements(By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'):
                print(f"✅ [{nome}] Iframe encontrado.")
                break
            print(f"⏳ [{nome}] Aguardando iframe... ({i+1}/5)")
            try:
                driver.get(LINK_AVIATOR)
            except:
                pass
            sleep(6)

        driver.save_screenshot("aviator2_aberto.png")
        print(f"📸 [{nome}] Screenshot salvo.")
        print(f"✅ [{nome}] Configurado com sucesso.")
        return True
    except Exception as e:
        print(f"❌ ERRO CRÍTICO {nome}: {e}")
        print(traceback.format_exc())
        try:
            driver.save_screenshot(f"erro_aviator2.png")
        except: pass
        return False

def find_game_elements(driver):
    try:
        driver.implicitly_wait(2)
        iframe = driver.find_element(By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]')
        driver.switch_to.frame(iframe)
        hist = driver.find_element(By.CSS_SELECTOR, ".payouts-block, app-stats-widget")
        driver.implicitly_wait(10)
        return iframe, hist
    except:
        driver.implicitly_wait(10)
        return None, None

def start_coleta(driver):
    print(f"🚀 [AVIATOR 2] Monitorando '{FIREBASE_PATH}'...")
    LAST_SENT = None
    ULTIMO_MULTIPLIER_TIME = time()
    data_atual = datetime.now(TZ_BR).date()
    estado_cookies = {'aceito': False}
    contador_debug = 0

    while True:
        now_br = datetime.now(TZ_BR)
        if (now_br.hour == HORA_REINICIO and now_br.minute >= MINUTO_REINICIO) or (now_br.hour == 0 and now_br.minute <= 5 and now_br.date() != data_atual):
            print(f"🌙 [AVIATOR 2] Reinício diário ({HORA_REINICIO}:{MINUTO_REINICIO:02d})...")
            break

        raw_text = None
        try:
            driver.switch_to.window(driver.current_window_handle)
            driver.switch_to.default_content()
            if contador_debug % 10 == 0:
                print(f"🔍 [DEBUG AVIATOR 2] URL: {driver.current_url} | Title: {driver.title}")
            contador_debug += 1

            iframe, hist_element = find_game_elements(driver)

            if not iframe:
                if contador_debug % 10 == 0:
                    print(f"⚠️ [AVIATOR 2] Iframe NÃO encontrado.")
            else:
                checar_e_aceitar_cookies_iframe(driver, estado_cookies)

            if not hist_element:
                if contador_debug % 30 == 0:
                    print(f"⚠️ [AVIATOR 2] Elemento histórico NÃO encontrado.")
            else:
                try:
                    first_payout = hist_element.find_element(
                        By.CSS_SELECTOR, ".payout:first-child, .bubble-multiplier:first-child"
                    )
                    raw_text = first_payout.get_attribute("innerText")
                    if not raw_text and contador_debug % 30 == 0:
                        print(f"⚠️ [AVIATOR 2] first_payout vazio.")
                except Exception as e:
                    if contador_debug % 30 == 0:
                        print(f"⚠️ [AVIATOR 2] Erro ao buscar payout: {e}")
        except Exception as e:
            if contador_debug % 30 == 0:
                print(f"⚠️ [AVIATOR 2] Exceção: {e}")

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
                        import uuid
                        key = now_br.strftime("%Y-%m-%d_%H-%M-%S") + "-" + str(uuid.uuid4().hex)[:8]
                        enviar_firebase_async(f"{FIREBASE_PATH}/{key}", payload)
                        print(f"🔥 [AVIATOR 2] {payload['multiplier']}x")
                        LAST_SENT = novo_valor
                        ULTIMO_MULTIPLIER_TIME = time()
                except: pass

        if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
            print(f"⚠️ [AVIATOR 2] Sem dados por {TEMPO_MAX_INATIVIDADE}s.")
            break

        sleep(POLLING_INTERVAL + 0.5)

def main():
    run_diagnostics()
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD.")
        sys.exit()
    print("==============================================")
    print("     AVIATOR 2 (VIP) - INICIADO (24H)        ")
    print("==============================================")
    limpar_pngs_antigos()

    while True:
        driver = None
        try:
            print("\n🔵 Iniciando ciclo Aviator 2...")
            driver = initialize_driver()
            if not driver:
                print("⚠️ Falha driver. Aguardando...")
                sleep(15)
                continue

            if setup_navegador(driver):
                start_coleta(driver)
            else:
                print("⚠️ Falha setup. Reiniciando...")
        except Exception as e:
            print(f"\n❌ ERRO CICLO AVIATOR 2: {e}")
            traceback.print_exc()
        finally:
            if driver:
                try:
                    driver.quit()
                    print("🗑️ Driver Aviator 2 encerrado.")
                except: pass
            gc.collect()
            sleep(5)

if __name__ == "__main__":
    main()
