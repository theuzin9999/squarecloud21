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
    cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
    firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})

# CONFIGURAÇÕES
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
URL_LOGIN = "https://go.goathbet.com/c/7vo"
LINK_AVIATOR_1 = "https://www.goathbet.bet/casino/spribe/aviator"
TZ_BR = pytz.timezone("America/Sao_Paulo")

def get_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    # Usa um User-Agent fixo e padrão
    options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    
    # Gerencia o driver automaticamente
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

def realizar_login(driver):
    driver.get(URL_LOGIN)
    wait = WebDriverWait(driver, 20)
    try:
        # Espera campo email
        email_field = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='email' or @name='email']")))
        email_field.send_keys(EMAIL)
        
        driver.find_element(By.XPATH, "//input[@type='password' or @name='password']").send_keys(PASSWORD)
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        time.sleep(10)
        print("✅ Login realizado.")
    except Exception as e:
        print(f"❌ Erro no login: {e}")

def monitorar_aviator(driver, url, path):
    driver.get(url)
    last_val = None
    while True:
        try:
            # Espera o Iframe do jogo
            iframe = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe")]')))
            driver.switch_to.frame(iframe)
            
            # Localiza o multiplicador
            mult = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".payouts-block, .bubble-multiplier")))
            
            valor = mult.text.replace('x', '').strip()
            if valor and valor != last_val:
                last_val = valor
                db.reference(path).push({
                    "multiplier": valor,
                    "time": datetime.now(TZ_BR).strftime("%H:%M:%S")
                })
                print(f"🔥 Coletado: {valor}x")
            
            driver.switch_to.default_content()
        except:
            driver.get(url) # Recarrega se cair
        time.sleep(1)

if __name__ == "__main__":
    driver = get_driver()
    realizar_login(driver)
    monitorar_aviator(driver, LINK_AVIATOR_1, "history")
