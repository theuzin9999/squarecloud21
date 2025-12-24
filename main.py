import os
import threading
import pytz
from time import sleep, time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import firebase_admin
from firebase_admin import credentials, db

# CONFIGURAÇÕES BÁSICAS
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
TZ_BR = pytz.timezone("America/Sao_Paulo")
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

CONFIG_BOTS = [
    {"nome": "AVIATOR_1", "link": "https://www.goathbet.com/pt/casino/spribe/aviator", "path": "history"},
    # """ PARA VOLTAR O AVIATOR 2 APAGUE ESTA LINHA E A ÚLTIMA DAS CONFIGS
    # {"nome": "AVIATOR_2", "link": "https://www.goathbet.com/pt/casino/spribe/aviator-2", "path": "aviator2"}
    # """
]

def init_firebase():
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})

def start_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1366,768")
    options.binary_location = "/usr/bin/chromium"
    return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)

def run_bot(config):
    nome, link, path_fb = config['nome'], config['link'], config['path']
    driver = start_driver()
    
    try:
        # LOGIN RÁPIDO
        driver.get("https://www.goathbet.com/pt/login")
        sleep(5)
        driver.find_element(By.NAME, "email").send_keys(EMAIL)
        driver.find_element(By.NAME, "password").send_keys(PASSWORD)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        sleep(8)
        
        driver.get(link)
        print(f"🚀 [{nome}] Scanner iniciado. Aguardando carregamento do jogo...")
        sleep(15) # Tempo para o iframe carregar

        last_sig = []
        
        while True:
            try:
                # 🛠️ O "INSPECIONAR" AUTOMÁTICO
                # Esse script abaixo faz o que você sugeriu: ele procura em todos os frames 
                # pelo bloco de payouts e devolve o texto pra gente.
                data = driver.execute_script("""
                    let frames = document.querySelectorAll('iframe');
                    for (let f of frames) {
                        try {
                            let doc = f.contentDocument || f.contentWindow.document;
                            let target = doc.querySelector('.payouts-block') || doc.querySelector('.payouts-wrapper') || doc.querySelector('app-stats-widget');
                            if (target && target.innerText.length > 5) return target.innerText;
                        } catch(e) {}
                    }
                    return null;
                """)

                if data:
                    # Limpa e converte os números
                    parts = data.replace('x', '').replace('\n', ' ').split()
                    mults = [float(p.replace(',', '.')) for p in parts if p.replace(',', '.').replace('.', '').isdigit()][:10]

                    if mults and mults != last_sig:
                        last_sig = mults
                        newest = mults[0]
                        
                        # Define a cor
                        cor = "blue-bg" if newest < 2.0 else "purple-bg" if newest < 10.0 else "magenta-bg"
                        
                        now = datetime.now(TZ_BR)
                        key = now.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                        
                        db.reference(f"{path_fb}/{key}").set({
                            "multiplier": f"{newest:.2f}",
                            "time": now.strftime("%H:%M:%S"),
                            "color": cor,
                            "date": now.strftime("%Y-%m-%d")
                        })
                        print(f"🔥 [{nome}] Capturado: {newest:.2f}x")

                sleep(2) # Evita sobrecarga
            except Exception as e:
                sleep(5)
                continue

    except Exception as e:
        print(f"❌ Erro no Bot {nome}: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    init_firebase()
    for cfg in CONFIG_BOTS:
        threading.Thread(target=run_bot, args=(cfg,)).start()
        sleep(10)
