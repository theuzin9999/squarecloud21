from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
# Removido: from webdriver_manager.chrome import ChromeDriverManager
from time import sleep, time
from datetime import datetime, date
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
import firebase_admin
from firebase_admin import credentials, db
import os
import pytz
import logging
from typing import Tuple, Optional

# =============================================================
# 🔥 CONFIGURAÇÃO GERAL
# =============================================================
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"
LINK_AVIATOR = "https://www.goathbet.com/pt/casino/spribe/aviator"

# Configuração de Logs
# logging.getLogger('WDM').setLevel(logging.ERROR) # Removido WDM
logging.getLogger('selenium').setLevel(logging.WARNING) # Silencia logs do Selenium
os.environ['WDM_LOG_LEVEL'] = '0'
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
TZ_BR = pytz.timezone("America/Sao_Paulo")

# ⚡ CONFIGURAÇÕES DE VELOCIDADE (TURBO)
POLLING_INTERVAL = 0.1          # Checa 10 vezes por segundo (Muito rápido)
INTERVALO_MINIMO_ENVIO = 0.1    # Sem delay artificial para envio
TEMPO_MAX_INATIVIDADE = 360     # 6 minutos

# =============================================================
# 🔧 INICIALIZAÇÃO FIREBASE
# =============================================================
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
    print("✅ Firebase conectado.")
except Exception as e:
    print(f"❌ ERRO FIREBASE: {e}")

# =============================================================
# 🛠️ FUNÇÕES DE NAVEGAÇÃO
# =============================================================
def start_driver() -> webdriver.Chrome:
    """
    Inicializa o driver do Chrome em modo Headless para Square Cloud/Cloud.
    Usa o caminho local do ChromeDriver.
    """
    options = webdriver.ChromeOptions()
    options.page_load_strategy = 'eager' # Carregamento instantâneo
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--headless")  # Roda sem interface gráfica
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3") # Mínimo de logs
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    options.add_argument("--silent")
    
    # Caminho do ChromeDriver em ambientes Debian/Ubuntu (Comum em Cloud)
    service = Service("/usr/lib/chromium-browser/chromedriver") 

    return webdriver.Chrome(service=service, options=options)

def safe_click(driver: webdriver.Chrome, by: str, value: str, timeout: int = 5) -> bool:
    """Tenta clicar em um elemento de forma segura."""
    try:
        element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        # Usa execute_script para clicar, mais robusto em headless
        driver.execute_script("arguments[0].click();", element)
        return True
    except:
        return False

def check_blocking_modals(driver: webdriver.Chrome):
    """Fecha modais críticos (+18 e Cookies)"""
    try:
        # Confirmação +18
        xpath_18 = [
            "//button[contains(., 'Sim')]", 
            "//div[contains(text(), '18 anos')]/..//button[contains(., 'Sim')]",
            "//button[contains(@class, 'MuiButton') and contains(., 'Sim')]",
            'button[data-age-action="yes"]' # Seletor CSS fallback
        ]
        for xpath in xpath_18:
            # Tenta como CSS Selector se for o último item
            by_method = By.XPATH if xpath.startswith('/') else By.CSS_SELECTOR
            if safe_click(driver, by_method, xpath, 1):
                sleep(0.5)
                break
        
        # Aceita Cookies
        safe_click(driver, By.XPATH, "//button[contains(., 'Aceitar todos')]", 1)
    except: 
        pass

def process_login(driver: webdriver.Chrome) -> bool:
    if not EMAIL or not PASSWORD:
        print("❌ ERRO: EMAIL ou PASSWORD não configurados.")
        return False
        
    print("➡️ Executando login rápido...")
    try:
        driver.get(URL_DO_SITE)
    except TimeoutException: 
        pass
    
    sleep(2)
    check_blocking_modals(driver)

    # 1. Tenta abrir a janela de login (Adicionado Fallbacks robustos)
    if safe_click(driver, By.CSS_SELECTOR, 'button[aria-label="Entrar"]', 4) or \
       safe_click(driver, By.XPATH, "//button[contains(., 'Entrar')]", 4) or \
       safe_click(driver, By.XPATH, "//a[contains(., 'Login') or contains(., 'Entrar')]", 4): # Fallback mais genérico
        
        sleep(0.5)
        try:
            # 2. Preenche e Envia credenciais
            driver.find_element(By.NAME, "email").send_keys(EMAIL)
            driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            
            # 3. Clica no botão de submissão
            if safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 4):
                print("✅ Login enviado.")
                sleep(4)
            check_blocking_modals(driver)
        except Exception as e: 
            print(f"⚠️ Erro ao preencher/enviar credenciais: {e}")
    else:
        print("⚠️ Botão de Login inicial não encontrado. Tentando continuar (Pode já estar logado).")
    
    # 4. Vai para o Aviator
    print("ℹ️ Abrindo Aviator...")
    driver.get(LINK_AVIATOR)
    
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe")]'))
        )
    except:
        sleep(3) # Fallback se o wait falhar
        
    check_blocking_modals(driver)
    return True

def initialize_game_elements(driver: webdriver.Chrome) -> Tuple[Optional[webdriver.remote.webelement.WebElement], Optional[webdriver.remote.webelement.WebElement]]:
    """Localiza elementos e imprime LOGS VISUAIS (apenas ao inicializar)"""
    POSSIVEIS_IFRAMES = [
        '//iframe[contains(translate(@src,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"salsagator")]',
        '//iframe[contains(@src, "spribe")]', # Prioridade alterada para o mais comum
        '//iframe[contains(@src, "/aviator/")]'
    ]
    
    POSSIVEIS_HISTORICOS = [
        ('.payouts-block', By.CSS_SELECTOR),
        ('div.payouts-block', By.CSS_SELECTOR),
        ('.rounds-history', By.CSS_SELECTOR),
        ('[data-testid="history"]', By.CSS_SELECTOR)
    ]

    driver.switch_to.default_content()
    iframe = None
    
    for xpath in POSSIVEIS_IFRAMES:
        try:
            iframe = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xpath)))
            driver.switch_to.frame(iframe)
            print(f"✅ Iframe encontrado com XPath: {xpath}")
            break
        except:
            driver.switch_to.default_content() # Garante reset para tentar proximo
            continue

    if not iframe:
        print("⚠️ Iframe não encontrado.")
        return None, None

    hist = None
    for selector, by_method in POSSIVEIS_HISTORICOS:
        try:
            hist = WebDriverWait(driver, 5).until(EC.presence_of_element_located((by_method, selector)))
            print(f"✅ Seletor de histórico encontrado: {selector}")
            break
        except: continue

    if not hist:
        print("⚠️ Histórico não encontrado.")
        driver.switch_to.default_content()
        return None, None

    return iframe, hist

def getColorClass(value: float) -> str:
    """Retorna a cor conforme o multiplicador."""
    if 1.0 <= value < 2.0: return "blue-bg"
    if 2.0 <= value < 10.0: return "purple-bg"
    if value >= 10.0: return "magenta-bg"
    return "default-bg"

# =============================================================
# 🤖 MOTOR DO ROBÔ (OTIMIZADO)
# =============================================================
def run_bot_session(relogin_done_for: date) -> Optional[date]:
    """
    Executa uma sessão completa do bot. Retorna a data se precisar de reinício diário.
    Levanta exceção em caso de falha crítica (Guardian Loop cuida do restart).
    """
    driver = None
    try:
        driver = start_driver()
        if not process_login(driver):
            raise Exception("Erro Login")

        iframe, hist = initialize_game_elements(driver)
        if not hist:
            raise Exception("Erro Elementos do Jogo não encontrados")

        print("✅ Captura TURBO iniciada (Logs limpos).\n")
        
        LAST_SENT = None
        ULTIMO_ENVIO = time()
        ULTIMO_MULTIPLIER_TIME = time()
        
        # Loop Infinito OTIMIZADO
        while True:
            # 1. Reinício 00:00 (Verifica no início de cada loop)
            now_br = datetime.now(TZ_BR)
            if now_br.hour == 0 and now_br.minute <= 5 and (relogin_done_for != now_br.date()):
                print(f"🕛 Reinício diário programado: {now_br.strftime('%H:%M:%S')}")
                driver.quit()
                return now_br.date()

            # 2. Inatividade
            if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                print(f"🚨 Sem resultados há {TEMPO_MAX_INATIVIDADE/60:.0f} min. Reiniciando...")
                raise Exception("Inatividade")

            # 3. LEITURA RÁPIDA
            try:
                # Tenta ler direto. Se falhar (Stale), vai pro except recuperar
                resultados = []
                
                # Tenta pegar itens individuais (mais preciso)
                items = hist.find_elements(By.CSS_SELECTOR, ".payouts-block .payout")
                if items:
                    for it in items:
                        txt = (it.text or "").strip().replace("x", "")
                        if txt:
                            try:
                                v = float(txt)
                                if v >= 1.0: resultados.append(v)
                            except: pass
                else:
                    # Fallback texto (menos preciso)
                    txt_full = (hist.text or "").replace('x', '').replace('\n', ' ')
                    for val in txt_full.split():
                        try:
                            v = float(val)
                            if v >= 1.0: resultados.append(v)
                        except: pass

                # 4. PROCESSAMENTO E ENVIO
                if resultados:
                    # Remove duplicatas mantendo ordem
                    seen = set()
                    resultados_unique = [x for x in resultados if not (x in seen or seen.add(x))]
                    
                    if resultados_unique:
                        novo = resultados_unique[0] # Novo resultado é sempre o primeiro
                        
                        # Se temos um novo resultado
                        if novo != LAST_SENT:
                            ULTIMO_MULTIPLIER_TIME = time() # Reseta o contador de inatividade
                            
                            if (time() - ULTIMO_ENVIO) > INTERVALO_MINIMO_ENVIO: # Controle de flood
                                
                                now_br = datetime.now(TZ_BR)
                                raw = f"{novo:.2f}"
                                entry_key = now_br.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                                time_display = now_br.strftime("%H:%M:%S")
                                
                                entry = {
                                    "multiplier": raw,
                                    "time": time_display,
                                    "color": getColorClass(novo),
                                    "date": now_br.strftime("%Y-%m-%d")
                                }
                                
                                try:
                                    # Salva no Firebase
                                    db.reference(f"history/{entry_key}").set(entry)
                                    print(f"🔥 {raw}x salvo às {time_display}") # Log Limpo
                                    LAST_SENT = novo
                                    ULTIMO_ENVIO = time()
                                except: 
                                    print("⚠️ Erro ao salvar no Firebase.")
                                    pass

                # Pausa Curta para Velocidade
                sleep(POLLING_INTERVAL)

            except (StaleElementReferenceException, TimeoutException, WebDriverException):
                # Ocorre se o iframe for recarregado ou a conexão cair
                print("⚠️ Conexão perdida com Iframe/Histórico. Reconectando elementos...")
                driver.switch_to.default_content()
                check_blocking_modals(driver) # Tenta fechar popups/modais
                iframe, hist = initialize_game_elements(driver)
                if not hist: raise Exception("Falha na reconexão") # Se não reconectar, reinicia a sessão

    except Exception as e:
        print(f"❌ Sessão encerrada: {e}")
        if driver:
            try: driver.quit()
            except: pass
        raise e # Levanta a exceção para o Guardian capturar

# =============================================================
# 🛡️ GUARDIÃO
# =============================================================
def run_guardian():
    print("\n==============================================")
    print("      GOATHBOT V5.0 (CLOUD TURBO LIMPO)")
    print("==============================================")
    relogin_date = date.today()
    
    while True:
        try:
            # Tenta rodar a sessão
            nova_data = run_bot_session(relogin_date)
            # Se retornar uma data, é um reinício programado (00:00)
            if nova_data: relogin_date = nova_data
        except KeyboardInterrupt:
            print("\n🛑 Bot parado manualmente.")
            break
        except:
            # Captura qualquer exceção (Erro Login, Inatividade, Falha na reconexão)
            print("🔄 Reiniciando sessão em 5s...")
            sleep(5)

if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❗ Configure as variáveis de ambiente EMAIL e PASSWORD.")
    else:
        run_guardian()
