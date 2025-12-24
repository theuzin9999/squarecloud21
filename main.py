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
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
import firebase_admin
from firebase_admin import credentials, db

# =============================================================
# 🔥 GOATHBOT V6.7 - ANTI-BOT BYPASS EDITION
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
    }
]

def run_network_diagnostics():
    print("\n--- 🕵️ DIAGNÓSTICO DE REDE RÁPIDO ---")
    try:
        ip = requests.get('https://api.ipify.org', timeout=10).text
        print(f"🌐 IP: {ip} | Status: {requests.get(URL_DO_SITE, timeout=10).status_code}")
    except: print("⚠️ Erro rápido de rede.")
    print("------------------------------------\n")

def start_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # --- NOVOS ARGUMENTOS ANTI-BLOQUEIO ---
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    chrome_options.binary_location = "/usr/bin/chromium"
    try:
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        # Esconde a flag de automação via script
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
        return driver
    except Exception as e:
        print(f"⚠️ Erro ao Iniciar Driver: {e}")
        return None

def human_type(element, text):
    """Digita como um humano para evitar detecção"""
    for char in text:
        element.send_keys(char)
        sleep(0.1)

def process_login(driver, target_link):
    print("🔑 Iniciando processo de login...")
    try:
        driver.get(URL_DO_SITE)
        sleep(6)
        
        # Tenta clicar no botão de Entrar usando múltiplos seletores
        login_selectors = [
            "//button[contains(text(), 'Entrar')]",
            "//a[contains(@href, 'login')]",
            ".login-button",
            "button.btn-login"
        ]
        
        clicked = False
        for selector in login_selectors:
            try:
                btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH if "//" in selector else By.CSS_SELECTOR, selector)))
                driver.execute_script("arguments[0].click();", btn)
                clicked = True
                break
            except: continue
        
        if not clicked:
            print("⚠️ Botão de login não encontrado, tentando ir direto para a URL de login...")
            driver.get(f"{URL_DO_SITE}/pt/login")
            sleep(4)

        # Preenchimento dos campos
        print("👤 Preenchendo credenciais...")
        user_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "email"))
        )
        pass_input = driver.find_element(By.NAME, "password")
        
        user_input.clear()
        human_type(user_input, EMAIL)
        sleep(1)
        pass_input.clear()
        human_type(pass_input, PASSWORD)
        sleep(1)
        
        submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        driver.execute_script("arguments[0].click();", submit_btn)
        
        # Verificação CRÍTICA: Espera o saldo aparecer
        print("⏳ Aguardando autenticação no site...")
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'balance')] | //a[contains(@href, 'deposit')]"))
        )
        print("✅ Login efetuado com sucesso!")
        
        driver.get(target_link)
        sleep(5)
        return True
    except Exception as e:
        print(f"❌ Erco no Login: Verifique se as credenciais estão corretas ou se há um Captcha.")
        return False

# ... (Restante do código de monitoramento permanece igual à V6.6)
