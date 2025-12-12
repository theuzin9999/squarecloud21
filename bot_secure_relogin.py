import threading
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURAÇÕES ---
# Coloque aqui sua integração com Firebase se necessário
def enviar_firebase(nome_bot, valor):
    # print(f"✅ [{nome_bot}] Enviando para Firebase: {valor}")
    pass

class AviatorMonitor:
    def __init__(self, nome, url, firebase_path):
        self.nome = nome
        self.url = url
        self.firebase_path = firebase_path
        self.ultimo_valor = None
        
        # Configuração do Chrome
        options = Options()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-notifications")
        # options.add_argument("--headless") # Descomente para rodar sem ver a janela
        
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    def iniciar(self):
        print(f"🔄 [{self.nome}] Iniciando driver e navegando...")
        self.driver.get(self.url)
        
        if self.preparar_jogo():
            self.monitorar()

    def preparar_jogo(self):
        """ Lógica robusta para entrar no iframe e carregar o histórico """
        try:
            wait = WebDriverWait(self.driver, 30)
            
            # 1. Aguarda o Iframe do jogo aparecer e entra nele
            print(f"🌍 [{self.nome}] Aguardando carregamento do jogo (Iframe)...")
            iframe = wait.until(EC.presence_of_element_located((By.XPATH, "//iframe[contains(@src, 'spribe')]")))
            self.driver.switch_to.frame(iframe)
            
            # 2. Aguarda o elemento do histórico (as bolinhas) aparecer
            print(f"🚀 [{self.nome}] Localizando histórico de velas...")
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "payouts-block")))
            
            print(f"✅ [{self.nome}] MONITORANDO COM SUCESSO!")
            return True
        except Exception as e:
            print(f"❌ [{self.nome}] Erro ao carregar jogo: {e}")
            self.driver.quit()
            return False

    def monitorar(self):
        while True:
            try:
                # Busca o primeiro item do histórico (o multiplicador mais recente)
                # O seletor '.payouts-block .bubble-multiplier' costuma ser o padrão Spribe
                elementos = self.driver.find_elements(By.CSS_SELECTOR, ".payouts-block .bubble-multiplier")
                
                if elementos:
                    valor_atual = elementos[0].text.replace('x', '').strip()
                    
                    if valor_atual != self.ultimo_valor:
                        self.ultimo_valor = valor_atual
                        print(f"🔥 [{self.nome}] NOVO MULTIPLICADOR: {valor_atual}x")
                        enviar_firebase(self.nome, valor_atual)
                
                time.sleep(1) # Delay para não sobrecarregar a CPU
            except Exception as e:
                print(f"⚠️ [{self.nome}] Erro durante monitoramento: {e}")
                time.sleep(5)
                # Se o iframe cair, tenta voltar para o foco principal e reentrar
                try:
                    self.driver.switch_to.default_content()
                    iframe = self.driver.find_element(By.XPATH, "//iframe[contains(@src, 'spribe')]")
                    self.driver.switch_to.frame(iframe)
                except:
                    pass

# --- EXECUÇÃO EM MULTI-THREADING ---

if __name__ == "__main__":
    print("==============================================")
    print("    GOATHBOT V6.2 - DUAL MONITORING STABLE    ")
    print("==============================================")

    # Definição dos bots
    bot_original = AviatorMonitor(
        "ORIGINAL", 
        "https://www.goathbet.com/pt/casino/spribe/aviator", 
        "history"
    )
    
    bot_aviator2 = AviatorMonitor(
        "AVIATOR 2", 
        "https://www.goathbet.com/pt/casino/spribe/aviator-2", 
        "aviator2"
    )

    # Criando as Threads para rodar os dois ao mesmo tempo
    t1 = threading.Thread(target=bot_original.iniciar)
    t2 = threading.Thread(target=bot_aviator2.iniciar)

    # Inicia os processos
    t1.start()
    t2.start()

    t1.join()
    t2.join()
