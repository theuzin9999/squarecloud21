import threading
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ==============================================================
#    GOATHBOT V6.3 - CLOUD STABLE EDITION (SQUARE CLOUD)
# ==============================================================

class AviatorMonitor:
    def __init__(self, nome, url, firebase_path):
        self.nome = nome
        self.url = url
        self.firebase_path = firebase_path
        self.ultimo_valor = None
        
        # --- CONFIGURAÇÃO CHROME (CRÍTICO PARA SQUARE CLOUD) ---
        options = Options()
        options.add_argument("--headless=new")  # Modo sem interface (Obrigatório)
        options.add_argument("--no-sandbox")    # Necessário para ambiente Docker
        options.add_argument("--disable-dev-shm-usage") # Evita crash por falta de memória
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Inicializa o driver
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            print(f"✅ [{self.nome}] Driver iniciado com sucesso.")
        except Exception as e:
            print(f"❌ [{self.nome}] Erro ao iniciar driver: {e}")

    def enviar_dados(self, valor):
        """ Espaço para sua lógica de Firebase/Telegram """
        print(f"🔥 [{self.nome}] NOVO MULTIPLICADOR: {valor}x")
        # Insira aqui: db.reference(self.firebase_path).set(valor)

    def entrar_no_jogo(self):
        """ Navega e foca no Iframe do Spribe """
        try:
            print(f"🌍 [{self.nome}] Navegando para: {self.url}")
            self.driver.get(self.url)
            wait = WebDriverWait(self.driver, 40)

            # 1. Espera o Iframe carregar (O ponto onde o Original costuma falhar)
            print(f"⏳ [{self.nome}] Aguardando Iframe do jogo...")
            iframe = wait.until(EC.presence_of_element_located((By.XPATH, "//iframe[contains(@src, 'spribe')]")))
            
            # 2. Muda o foco do Selenium para dentro do Iframe
            self.driver.switch_to.frame(iframe)
            print(f"🎯 [{self.nome}] Foco definido para o Iframe.")

            # 3. Espera o histórico de velas aparecer
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "payouts-block")))
            print(f"🚀 [{self.nome}] MONITORAMENTO INICIADO!")
            return True
        except Exception as e:
            print(f"❌ [{self.nome}] Erro ao entrar no jogo: {e}")
            return False

    def monitorar(self):
        if not self.entrar_no_jogo():
            return

        while True:
            try:
                # Localiza todos os multiplicadores no histórico
                historico = self.driver.find_elements(By.CSS_SELECTOR, ".payouts-block .bubble-multiplier")
                
                if historico:
                    # Pega o valor da vela mais recente (primeira da lista)
                    valor_atual = historico[0].text.replace('x', '').strip()

                    # Verifica se o valor mudou para evitar duplicatas
                    if valor_atual != self.ultimo_valor and valor_atual != "":
                        self.ultimo_valor = valor_atual
                        self.enviar_dados(valor_atual)
                
                time.sleep(1.5) # Intervalo para não sobrecarregar CPU da Square Cloud

            except Exception as e:
                # Se der erro (ex: página atualizou), tenta refocar no iframe
                try:
                    self.driver.switch_to.default_content()
                    iframe = self.driver.find_element(By.XPATH, "//iframe[contains(@src, 'spribe')]")
                    self.driver.switch_to.frame(iframe)
                except:
                    print(f"⚠️ [{self.nome}] Tentando recuperar conexão...")
                    time.sleep(5)

# --- FUNÇÃO DE EXECUÇÃO ---

def rodar_original():
    bot = AviatorMonitor(
        "ORIGINAL", 
        "https://www.goathbet.com/pt/casino/spribe/aviator", 
        "history"
    )
    bot.monitorar()

def rodar_aviator2():
    bot = AviatorMonitor(
        "AVIATOR 2", 
        "https://www.goathbet.com/pt/casino/spribe/aviator-2", 
        "aviator2"
    )
    bot.monitorar()

if __name__ == "__main__":
    print("==============================================")
    print("    GOATHBOT V6.3 - DUAL MONITORING STABLE    ")
    print("==============================================")

    # Criando as Threads
    t1 = threading.Thread(target=rodar_original)
    t2 = threading.Thread(target=rodar_aviator2)

    # Iniciando
    t1.start()
    t2.start()

    # Mantém o script rodando
    t1.join()
    t2.join()
