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

# CONFIGURAÇÕES
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
TZ_BR = pytz.timezone("America/Sao_Paulo")
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

# CONFIGURAÇÃO DOS BOTS (Adicionado o marcador solicitado)
CONFIG_BOTS = [
    {"nome": "AVIATOR_1", "link": "https://www.goathbet.com/pt/casino/spribe/aviator", "path": "history"},
    # 👇👇👇 (APAGUE AQUI PARA VOLTAR O AVIATOR 2) 👇👇👇
    # {"nome": "AVIATOR_2", "link": "https://www.goathbet.com/pt/casino/spribe/aviator-2", "path": "aviator2"}
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
        # LOGIN
        driver.get("https://www.goathbet.com/pt/login")
        sleep(5)
        try:
            driver.find_element(By.NAME, "email").send_keys(EMAIL)
            driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
            sleep(8)
        except: pass
        
        driver.get(link)
        print(f"🚀 [{nome}] Iniciando Inspeção Automática...")
        sleep(15) 

        last_sig = []
        
        while True:
            try:
                # 🛠️ A MÁGICA DO "INSPECIONAR":
                # Este script varre a página procurando o iframe correto e 
                # extrai o texto dos multiplicadores diretamente do código-fonte interno.
                # Prioridade: payouts-block (novo) -> payouts-wrapper (visual) -> stats (antigo)
                data = driver.execute_script("""
                    function getStats() {
                        let frames = document.querySelectorAll('iframe');
                        for (let f of frames) {
                            try {
                                let doc = f.contentDocument || f.contentWindow.document;
                                // Tenta todos os seletores conhecidos de uma vez
                                let target = doc.querySelector('.payouts-block') || 
                                             doc.querySelector('.payouts-wrapper') || 
                                             doc.querySelector('app-stats-widget') ||
                                             doc.querySelector('.stats-list');
                                             
                                if (target && target.innerText.length > 3) {
                                    return target.innerText;
                                }
                            } catch(e) {}
                        }
                        return null;
                    }
                    return getStats();
                """)

                if data:
                    # Filtra apenas os números (ex: 1.50, 2.00)
                    parts = data.replace('x', '').replace('\n', ' ').split()
                    mults = []
                    for p in parts:
                        try:
                            val = float(p.replace(',', '.'))
                            if val >= 1.0: mults.append(val)
                        except: pass

                    # Só envia se a lista mudou (evita duplicados)
                    if mults and mults[:5] != last_sig:
                        last_sig = mults[:5]
                        newest = mults[0]
                        
                        cor = "blue-bg" if newest < 2.0 else "purple-bg" if newest < 10.0 else "magenta-bg"
                        
                        now = datetime.now(TZ_BR)
                        key = now.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                        
                        db.reference(f"{path_fb}/{key}").set({
                            "multiplier": f"{newest:.2f}",
                            "time": now.strftime("%H:%M:%S"),
                            "color": cor,
                            "date": now.strftime("%Y-%m-%d")
                        })
                        print(f"🔥 [{nome}] NOVO RESULTADO: {newest:.2f}x")

                sleep(1) 
            except Exception:
                sleep(2)
                continue

    except Exception as e:
        print(f"❌ Erro Crítico: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    init_firebase()
    # Filtra apenas o que não for string (comentário)
    active = [c for c in CONFIG_BOTS if isinstance(c, dict)]
    for cfg in active:
        threading.Thread(target=run_bot, args=(cfg,)).start()
        sleep(5)
