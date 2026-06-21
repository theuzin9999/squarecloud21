import os
import sys
import threading
import time
from datetime import datetime
import pytz
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import firebase_admin
from firebase_admin import credentials, db

# CONFIGURAÇÃO FIREBASE
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate(SERVICE_ACCOUNT_FILE), {'databaseURL': DATABASE_URL})

# CONFIGURAÇÕES
URL_LOGIN = "https://go.goathbet.com/c/7vo"
LINK_AVIATOR_1 = "https://www.goathbet.bet/casino/spribe/aviator"
LINK_AVIATOR_2 = "https://www.goathbet.bet/casino/spribe/aviator-vip"
TZ_BR = pytz.timezone("America/Sao_Paulo")

def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    # O User-Agent deve ser padrão e simples
    chrome_options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    return driver

def realizar_login(driver):
    driver.get(URL_LOGIN)
    time.sleep(10)
    try:
        driver.find_element(By.XPATH, "//input[@id='email' or @name='email']").send_keys(os.getenv("EMAIL"))
        driver.find_element(By.XPATH, "//input[@id='password' or @name='password']").send_keys(os.getenv("PASSWORD"))
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        time.sleep(15)
    except Exception as e:
        print(f"Erro no login: {e}")

def monitorar_jogo(driver, url, path_firebase):
    driver.get(url)
    last_val = None
    while True:
        try:
            # Espera resiliente para encontrar o iframe e o elemento
            iframe = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe")]')))
            driver.switch_to.frame(iframe)
            elemento = WebDriverWait(driver, 15).until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".payouts-block, .bubble-multiplier")))
            
            val_text = elemento.text.replace('x', '').strip()
            if val_text and val_text != last_val:
                last_val = val_text
                payload = {"multiplier": val_text, "time": datetime.now(TZ_BR).strftime("%H:%M:%S")}
                db.reference(path_firebase).push(payload)
                print(f"Coletado {path_firebase}: {val_text}")
            
            driver.switch_to.default_content()
        except Exception:
            driver.get(url)
        time.sleep(2)

if __name__ == "__main__":
    driver = get_driver()
    realizar_login(driver)
    
    # Executa em uma thread para manter o controle
    threading.Thread(target=monitorar_jogo, args=(driver, LINK_AVIATOR_1, "history"), daemon=True).start()
    
    while True:
        time.sleep(60)
