import os
import logging
import threading
import pytz
import gc
from time import sleep, time
from datetime import datetime, date
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
import firebase_admin
from firebase_admin import credentials, db

# =============================================================
# 🔥 GOATHBOT V6.6 - FIX SELETOR POR IMAGEM DEVS
# =============================================================

SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"
TZ_BR = pytz.timezone("America/Sao_Paulo")

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

CONFIG_BOTS = [
    {
        "nome": "AVIATOR_1",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator",
        "firebase_path": "history"
    },
    # ==============================================================================
    # ⬇️ APAGUE AS 3 ASPAS ABAIXO (''' ) PARA VOLTAR O AVIATOR 2
    # ==============================================================================
    '''
    {
        "nome": "AVIATOR_2",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator-2",
        "firebase_path": "aviator2"
    },
    '''
    # ==============================================================================
    # ⬆️ APAGUE AS 3 ASPAS ACIMA ( ''') PARA VOLTAR O AVIATOR 2
    # ==============================================================================
]

def init_firebase():
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
            firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
            print("✅ Firebase Conectado.")
        except Exception as e:
            print(f"❌ Erro Crítico Firebase: {e}")
            exit(1)

def start_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080") # Aumentado para garantir renderização
    chrome_options.binary_location = "/usr/bin/chromium"
    try:
        service = Service("/usr/bin/chromedriver")
        return webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"⚠️ Erro Driver: {e}")
        return None

def process_login(driver, target_link):
    print("🔑 Efetuando Login...")
    try:
        driver.get(URL_DO_SITE)
        sleep(5)
        # Tenta clicar no botão entrar se existir
        btns = driver.find_elements(By.XPATH, "//button[contains(., 'Entrar')]")
        if btns:
            btns[0].click()
            sleep(2)
            driver.find_element(By.NAME, "email").send_keys(EMAIL)
            driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
            sleep(5)
    except: pass
    driver.get(target_link)
    sleep(10) # Tempo maior para carregar o iframe pesado

def get_game_elements(driver):
    try:
        driver.switch_to.default_content()
        
        # Busca o iframe especificamente pela classe vista no seu print
        iframe = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "iframe.game-iframe"))
        )
        driver.switch_to.frame(iframe)
        
        # Busca o wrapper do histórico conforme seu print
        # O seletor .payouts-block é o container direto dos multiplicadores
        hist = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.payouts-block"))
        )
        return hist
    except Exception as e:
        print(f"❌ Erro ao localizar elementos no Iframe: {e}")
        return None

def get_color_class(value):
    try:
        m = float(value)
        if 1.0 <= m < 2.0: return "blue-bg"
        if 2.0 <= m < 10.0: return "purple-bg"
        return "magenta-bg"
    except: return "default-bg"

def run_bot_thread(config):
    if isinstance(config, str): return
    nome, link, path_fb = config['nome'], config['link'], config['firebase_path']
    
    while True:
        driver = start_driver()
        if not driver: continue
        try:
            process_login(driver, link)
            hist_element = get_game_elements(driver)
            
            if not hist_element:
                driver.quit()
                continue

            last_signature = []
            inactivity_timer = time()

            while True:
                if (time() - inactivity_timer) > 300: break # Reset se travar 5 min

                try:
                    # Extração direta do texto dos payouts
                    text_data = driver.execute_script("return arguments[0].innerText;", hist_element)
                    if text_data:
                        multipliers = []
                        for val in text_data.replace('x', '').split():
                            try:
                                v = float(val)
                                if v >= 1.0: multipliers.append(v)
                            except: pass

                        if multipliers and multipliers[:5] != last_signature:
                            inactivity_timer = time()
                            last_signature = multipliers[:5]
                            newest = multipliers[0]
                            
                            now_save = datetime.now(TZ_BR)
                            key = now_save.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                            db.reference(f"{path_fb}/{key}").set({
                                "multiplier": f"{newest:.2f}",
                                "time": now_save.strftime("%H:%M:%S"),
                                "color": get_color_class(newest),
                                "date": now_save.strftime("%Y-%m-%d")
                            })
                            print(f"🔥 [{nome}] {newest:.2f}x")
                    sleep(1.5)
                except:
                    break
        except Exception as e:
            print(f"⚠️ Erro no loop {nome}: {e}")
        finally:
            driver.quit()
            sleep(5)

if __name__ == "__main__":
    init_firebase()
    active_bots = [b for b in CONFIG_BOTS if isinstance(b, dict)]
    threads = []
    for cfg in active_bots:
        t = threading.Thread(target=run_bot_thread, args=(cfg,))
        t.start()
        threads.append(t)
        sleep(40)
