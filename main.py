import os
import threading
import time
from datetime import datetime
import pytz
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import firebase_admin
from firebase_admin import credentials, db

# ... (Configurações de Firebase permanecem iguais) ...

def get_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    options.binary_location = "/usr/bin/chromium"
    return webdriver.Chrome(options=options)

def realizar_login(driver):
    driver.get(URL_LOGIN)
    print("⏳ Aguardando carregamento da página de login...")
    
    # Aumentamos o tempo de espera para 30 segundos e usamos WebDriverWait
    wait = WebDriverWait(driver, 30)
    
    try:
        # Tenta encontrar o campo por diferentes seletores comuns
        campo_email = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='email' or @name='email' or @id='email']")))
        campo_email.send_keys(os.getenv("EMAIL"))
        
        campo_pass = driver.find_element(By.XPATH, "//input[@type='password' or @name='password' or @id='password']")
        campo_pass.send_keys(os.getenv("PASSWORD"))
        
        btn_submit = driver.find_element(By.XPATH, "//button[@type='submit']")
        btn_submit.click()
        
        print("✅ Login enviado com sucesso.")
        time.sleep(15) # Espera o redirecionamento pós-login
    except Exception as e:
        # Se falhar, salva um print para debug na Square Cloud
        driver.save_screenshot("erro_login.png")
        print(f"❌ Erro crítico ao localizar elementos de login: {e}")

# ... (restante do código igual)
