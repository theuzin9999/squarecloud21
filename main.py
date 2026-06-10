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

SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"
TZ_BR = pytz.timezone("America/Sao_Paulo")

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

CONFIG_BOTS = [
    {"nome": "AVIATOR_1", "link": "https://www.goathbet.com/pt/casino/spribe/aviator", "firebase_path": "history"}
]
CONFIG_BOTS.append({"nome": "AVIATOR_2", "link": "https://www.goathbet.com/casino/spribe/aviator-vip", "firebase_path": "aviator2"})

logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

def run_diagnostics():
    print("\n--- DIAGNOSTICO ---")
    try:
        ip = requests.get('https://api.ipify.org', timeout=10).text
        print(f"IP: {ip}")
        res = requests.get(URL_DO_SITE, timeout=10)
        print(f"Status Site: {res.status_code}")
    except Exception as e:
        print(f"Erro rede: {e}")
    print("-------------------\n")

def init_firebase():
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
            firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
            print("Firebase OK")
        except Exception as e:
            print(f"Erro Firebase: {e}")
            exit(1)

def start_driver():
    options = Options()
    options.page_load_strategy = 'eager'
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--mute-audio")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.binary_location = "/usr/bin/chromium"
    try:
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)
        # CDP stealth
        driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"})
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"})
        return driver
    except Exception as e:
        print(f"Erro driver: {e}")
        return None

def process_login(driver, target_link):
    try:
        driver.get(URL_DO_SITE)
        sleep(5)
        for xpath in ["//button[contains(., 'Sim')]", "//button[contains(., 'Aceitar')]", "//button[contains(., 'Fechar')]"]:
            try:
                for btn in driver.find_elements(By.XPATH, xpath):
                    if btn.is_displayed(): btn.click()
            except: pass
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Entrar')]"))).click()
        sleep(2)
        driver.find_element(By.NAME, "email").send_keys(EMAIL)
        driver.find_element(By.NAME, "password").send_keys(PASSWORD)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        sleep(10)
    except Exception as e:
        print(f"Aviso login: {e}")
    driver.get(target_link)
    sleep(8)
    try:
        WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.TAG_NAME, 'iframe')))
        return True
    except: return False

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
    except: return None

def get_color_class(value):
    try:
        m = float(value)
        if 1.0 <= m < 2.0: return "blue-bg"
        if 2.0 <= m < 10.0: return "purple-bg"
        if m >= 10.0: return "magenta-bg"
    except: pass
    return "default-bg"

def run_bot_thread(config):
    nome = config['nome']
    link = config['link']
    path_fb = config['firebase_path']
    last_sent = None
    while True:
        driver = None
        try:
            print(f"[{nome}] Iniciando...")
            driver = start_driver()
            if not driver: 
                sleep(10); continue
            if not process_login(driver, link):
                driver.quit(); sleep(5); continue
            hist_el = get_game_elements(driver)
            if not hist_el:
                driver.quit(); continue
            print(f"[{nome}] Monitorando...")
            inactivity_timer = time()
            while True:
                now = datetime.now(TZ_BR)
                if now.hour == 23 and now.minute == 59:
                    break
                if (time() - inactivity_timer) > 360:
                    break
                try:
                    try:
                        raw = driver.execute_script("return arguments[0].querySelector('[appcoloredmultiplier].payout:first-child, .payout:first-child').innerText", hist_el)
                    except: raw = None
                    if raw:
                        clean = raw.strip().lower().replace('x', '').replace(',', '')
                        if clean:
                            try:
                                val = float(clean)
                                if val != last_sent:
                                    last_sent = val
                                    now_save = datetime.now(TZ_BR)
                                    key = now_save.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                                    data = {
                                        "multiplier": f"{val:.2f}",
                                        "time": now_save.strftime("%H:%M:%S"),
                                        "color": get_color_class(val),
                                        "date": now_save.strftime("%Y-%m-%d")
                                    }
                                    db.reference(f"{path_fb}/{key}").set(data)
                                    print(f"[{nome}] {data['multiplier']}x")
                                    inactivity_timer = time()
                            except: pass
                    sleep(1)
                except (StaleElementReferenceException, NoSuchElementException):
                    hist_el = get_game_elements(driver)
                    if not hist_el: break
        except Exception as e:
            print(f"[{nome}] Erro: {e}")
            sleep(5)
        finally:
            if driver: 
                try: driver.quit()
                except: pass
            gc.collect()
            sleep(10)

if __name__ == "__main__":
    run_diagnostics()
    if not EMAIL or not PASSWORD:
        print("Configure EMAIL e PASSWORD!")
    else:
        init_firebase()
        threads = []
        print(f"Iniciando {len(CONFIG_BOTS)} bots...")
        for i, cfg in enumerate(CONFIG_BOTS):
            t = threading.Thread(target=run_bot_thread, args=(cfg,))
            t.start()
            threads.append(t)
            if i < len(CONFIG_BOTS) - 1:
                sleep(40)
        for t in threads:
            t.join()
