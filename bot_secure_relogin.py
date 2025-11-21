from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
# Em ambiente Cloud, usamos o caminho local do ChromeDriver
from time import sleep, time
from datetime import datetime, date
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
import os
import pytz
import logging
from typing import Tuple, Optional

# Desabilita logs verbosos do Selenium
logging.getLogger('selenium').setLevel(logging.WARNING)

# =============================================================
# 🔥 CONFIGURAÇÃO FIREBASE
# =============================================================
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'

try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {
            'databaseURL': DATABASE_URL
        })
    print("✅ Firebase Admin SDK inicializado com sucesso. O bot salvará dados.")
except FileNotFoundError:
    print("\n❌ ERRO CRÍTICO: Arquivo de credenciais 'serviceAccountKey.json' não encontrado.")
    print("Baixe a chave JSON do console do Firebase e coloque na mesma pasta deste script.")
    exit()
except Exception as e:
    print(f"\n❌ ERRO DE CONEXÃO FIREBASE: {e}")
    # Não damos exit, pois a lógica de reconexão pode tentar novamente

# =============================================================
# ⚙️ VARIÁVEIS PRINCIPAIS (TURBO SPEED)
# =============================================================
URL_DO_SITE = "https://www.goathbet.com"
# Ajustado para o formato mais comum no bot_secure_relogin.py (pt/casino)
LINK_AVIATOR = "https://www.goathbet.com/pt/casino/spribe/aviator" 

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

POLLING_INTERVAL = 0.1          # ⚡ Turbo: Intervalo de checagem (0.1 segundo)
INTERVALO_MINIMO_ENVIO = 0.1    # ⚡ Turbo: Mínimo de tempo entre dois envios (segundos)
TEMPO_MAX_INATIVIDADE = 360     # 6 minutos (360 segundos)
TZ_BR = pytz.timezone("America/Sao_Paulo")

# =============================================================
# 🔧 FUNÇÕES AUXILIARES
# =============================================================
def getColorClass(value: float) -> str:
    """Retorna a cor conforme o multiplicador."""
    if 1.0 <= value < 2.0:
        return "blue-bg"
    if 2.0 <= value < 10.0:
        return "purple-bg"
    if value >= 10.0:
        return "magenta-bg"
    return "default-bg"

def safe_click(driver: webdriver.Chrome, by: str, value: str, timeout: int = 5) -> bool:
    """Tenta clicar em um elemento de forma segura."""
    try:
        # Usa execute_script para clicar, mais robusto em headless
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        driver.execute_script("arguments[0].click();", el)
        return True
    except Exception:
        return False

def safe_find(driver: webdriver.Chrome, by: str, value: str, timeout: int = 5):
    """Tenta encontrar um elemento de forma segura."""
    try:
        return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))
    except Exception:
        return None

def check_blocking_modals(driver: webdriver.Chrome):
    """Fecha modais críticos (+18 e Cookies)"""
    try:
        # Confirma maior de 18
        xpath_18 = "//button[contains(., 'Sim')]"
        if safe_click(driver, By.XPATH, xpath_18, 1) or \
           safe_click(driver, By.CSS_SELECTOR, 'button[data-age-action="yes"]', 1):
            sleep(0.5)
        # Aceita cookies
        safe_click(driver, By.XPATH, "//button[contains(., 'Aceitar')]", 1)
    except: 
        pass

def initialize_game_elements(driver: webdriver.Chrome) -> Tuple[Optional[webdriver.remote.webelement.WebElement], Optional[webdriver.remote.webelement.WebElement]]:
    """
    Localiza iframe e histórico do Aviator com prioridade atualizada.
    """
    # 🎯 Prioridade 1: spribe (novo do site)
    POSSIVEIS_IFRAMES = [
        '//iframe[contains(@src, "spribe")]',
        '//iframe[contains(translate(@src,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"salsagator")]',
        '//iframe[contains(@src, "/aviator/")]',
        '//iframe[contains(translate(@src,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"game?token")]',
        '//iframe[contains(@src, "aviator-game")]'
    ]

    # 🎯 Prioridade 1: .payouts-block (novo do jogo)
    POSSIVEIS_HISTORICOS = [
        ('.payouts-block', By.CSS_SELECTOR),
        ('div.payouts-block', By.CSS_SELECTOR),
        # fallbacks
        ('.rounds-history', By.CSS_SELECTOR),
        ('.history-list', By.CSS_SELECTOR),
        ('[data-testid="history"]', By.CSS_SELECTOR)
    ]

    iframe = None
    
    driver.switch_to.default_content()

    for xpath in POSSIVEIS_IFRAMES:
        try:
            iframe = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            driver.switch_to.frame(iframe)
            print(f"✅ Iframe encontrado com XPath: {xpath}")
            break
        except Exception:
            driver.switch_to.default_content()
            continue

    if not iframe:
        print("⚠️ Nenhum iframe encontrado. Verifique se o jogo está carregado.")
        return None, None

    historico_elemento = None
    for selector, by_method in POSSIVEIS_HISTORICOS:
        try:
            # Tempo reduzido para achar o histórico dentro do iframe
            historico_elemento = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((by_method, selector))
            )
            print(f"✅ Seletor de histórico encontrado: {selector}")
            break
        except Exception:
            continue

    if not historico_elemento:
        print("⚠️ Nenhum seletor de histórico encontrado! O bot pode congelar.")
        driver.switch_to.default_content()
        return None, None

    return iframe, historico_elemento

# =============================================================
# 🛠️ FUNÇÕES DE NAVEGAÇÃO
# =============================================================
def start_driver():
    options = webdriver.ChromeOptions()
    options.page_load_strategy = 'eager' # Carregamento instantâneo
    options.add_argument("--log-level=3")
    options.add_argument("--silent")
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    options.add_argument("--start-maximized")
    options.add_argument("--disable-popup-blocking")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def safe_click(driver, by, value, timeout=5):
    try:
        element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        driver.execute_script("arguments[0].click();", element)
        return True
    except:
        return False

def check_blocking_modals(driver):
    """Fecha modais críticos (+18 e Cookies)"""
    try:
        xpath_18 = [
            "//button[contains(., 'Sim')]", 
            "//div[contains(text(), '18 anos')]/..//button[contains(., 'Sim')]",
            "//button[contains(@class, 'MuiButton') and contains(., 'Sim')]"
        ]
        for xpath in xpath_18:
            if safe_click(driver, By.XPATH, xpath, 1):
                sleep(0.5)
                break
        safe_click(driver, By.XPATH, "//button[contains(., 'Aceitar todos')]", 1)
    except: pass

def process_login(driver):
    print("➡️ Executando login rápido...")
    try:
        driver.get(URL_DO_SITE)
    except TimeoutException: pass
    
    sleep(2)
    check_blocking_modals(driver)

    # Tenta logar
    if safe_click(driver, By.CSS_SELECTOR, 'button[aria-label="Entrar"]', 4) or \
       safe_click(driver, By.XPATH, "//button[contains(., 'Entrar')]", 4):
        
        sleep(0.5)
        try:
            driver.find_element(By.NAME, "email").send_keys(EMAIL)
            driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            if safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 4):
                print("✅ Login enviado.")
                sleep(4)
            check_blocking_modals(driver)
        except: pass
    
    print("ℹ️ Abrindo Aviator...")
    driver.get(LINK_AVIATOR)
    # Aguarda carregar o contexto do jogo
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe")]'))
        )
    except:
        sleep(3) # Fallback se o wait falhar
        
    check_blocking_modals(driver)
    return True

def initialize_game_elements(driver):
    """Localiza elementos e imprime LOGS VISUAIS (apenas ao inicializar)"""
    POSSIVEIS_IFRAMES = [
        '//iframe[contains(translate(@src,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"salsagator")]',
        '//iframe[contains(@src, "/aviator/")]',
        '//iframe[contains(@src, "spribe")]'
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

def getColorClass(value):
    m = float(value)
    if 1.0 <= m < 2.0: return "blue-bg"
    if 2.0 <= m < 10.0: return "purple-bg"
    if m >= 10.0: return "magenta-bg"
    return "default-bg"

# =============================================================
# 🚀 LOOP PRINCIPAL (TURBO OTIMIZADO)
# =============================================================
def run_bot_session(relogin_done_for: date) -> Optional[date]:
    """
    Executa uma sessão do bot. 
    Retorna a data se o reinício diário for necessário, senão levanta exceção.
    """
    driver = None
    try:
        driver = start_driver()

        # === FLUXO DE INICIALIZAÇÃO ===
        if not process_login(driver):
            raise Exception("Falha crítica no login")

        iframe, hist = initialize_game_elements(driver)

        if not hist:
            raise Exception("Falha crítica: Elementos do jogo não encontrados.")

        LAST_SENT = None
        ULTIMO_ENVIO = time()
        ULTIMO_MULTIPLIER_TIME = time()
        
        print("✅ Captura TURBO iniciada (foco no iframe para velocidade).\n")

        while True:
            # === VERIFICAÇÕES DE GUARDIÃO ===
            now_br = datetime.now(TZ_BR)
            
            # Reinício Diário (00:00)
            if now_br.hour == 0 and now_br.minute <= 5 and (relogin_done_for != now_br.date()):
                print(f"🕛 REINÍCIO PROGRAMADO: {now_br.strftime('%H:%M:%S')}. Sinalizando reinício...")
                driver.quit()
                return now_br.date() # Retorna a data para o Guardian gerenciar

            # Inatividade
            if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                print(f"🚨 Inatividade por mais de {TEMPO_MAX_INATIVIDADE/60:.0f} minutos. Reiniciando...")
                raise Exception("Inatividade") # Força o reinício pelo Guardian

            # === RECONEXÃO COM IFRAME E LEITURA ===
            try:
                # 1. Tenta manter o foco no iframe para leitura
                driver.switch_to.frame(iframe) 

                # 2. Leitura Rápida
                resultados = []
                
                # Tenta pegar itens individuais (mais preciso)
                items = hist.find_elements(By.CSS_SELECTOR, ".payouts-block .payout")
                if items:
                    for it in items:
                        txt = (it.text or "").strip().lower().replace("x", "")
                        if txt:
                            try:
                                v = float(txt)
                                if v >= 1.0: resultados.append(v)
                            except ValueError: pass
                else:
                    # Fallback: texto bruto (mais lento, mas seguro)
                    resultados_texto = (hist.text or "").strip().replace('x', '').replace('\n', ' ')
                    for val in resultados_texto.split():
                        try:
                            v = float(val)
                            if v >= 1.0: resultados.append(v)
                        except: pass
                
                # 3. Processamento e Envio
                if resultados:
                    # Remove duplicatas, preservando ordem (Foco no item mais recente = resultados[0])
                    seen = set()
                    resultados_unique = [x for x in resultados if not (x in seen or seen.add(x))]
                    
                    if resultados_unique:
                        novo = resultados_unique[0]
                        
                        if novo != LAST_SENT:
                            
                            # Não precisa de ULTIMO_ENVIO aqui, pois o POLLING_INTERVAL já é o controle de velocidade.
                            # Mas mantemos para futura expansão, se o bot enviar resultados rápido demais (seguro)
                            if (time() - ULTIMO_ENVIO) > INTERVALO_MINIMO_ENVIO:

                                now_br = datetime.now(TZ_BR)
                                raw = f"{novo:.2f}"
                                # Garante unicidade da key
                                entry_key = now_br.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-') 
                                time_display = now_br.strftime("%H:%M:%S")
                                color = getColorClass(novo)

                                entry = {"multiplier": raw, "time": time_display, "color": color, "date": now_br.strftime("%Y-%m-%d")}

                                try:
                                    # SALVA APENAS
                                    db.reference(f"history/{entry_key}").set(entry)
                                    print(f"🔥 {raw}x salvo às {time_display}") # Log Limpo
                                except Exception as e:
                                    print("⚠️ Erro ao salvar:", e)

                                LAST_SENT = novo
                                ULTIMO_ENVIO = time()
                                ULTIMO_MULTIPLIER_TIME = time()  # Reseta o timer de inatividade

            except (StaleElementReferenceException, TimeoutException, WebDriverException):
                # Ocorre quando o iframe é recarregado ou a conexão cai
                print("⚠️ Conexão perdida com Iframe/Histórico. Reconectando elementos...")
                driver.switch_to.default_content() # Volta para o documento principal
                check_blocking_modals(driver) # Tenta fechar popups
                iframe, hist = initialize_game_elements(driver)
                if not hist: 
                    raise Exception("Falha na reconexão") # Joga para o guardian loop reiniciar

            # Não faz switch_to.default_content() aqui para manter o foco no iframe e ganhar velocidade
            sleep(POLLING_INTERVAL)

    except Exception as e:
        print(f"❌ Erro na sessão: {e}")
        if driver:
            try: driver.quit()
            except: pass
        raise e # Levanta a exceção para o Guardian capturar

# =============================================================
# 🛡️ GUARDIÃO
# =============================================================
def run_guardian():
    print("\n==============================================")
    print("  GOATHBOT V4.3 (ONLINE TURBO PRIORIZADO)")
    print("==============================================")
    relogin_date = date.today() # Data do último login/restart. Evita restart repetido à 00:00
    
    while True:
        try:
            # Tenta rodar a sessão
            new_date = run_bot_session(relogin_date)
            # Se a sessão retornar uma data, significa que é um reinício programado (00:00)
            if new_date: relogin_date = new_date
            
        except KeyboardInterrupt:
            print("\n🛑 Bot parado manualmente.")
            break
        except Exception:
            # Captura qualquer outro erro (login falhou, elementos não encontrados, inatividade, etc.)
            print("🔄 Reiniciando em 5s...")
            sleep(5)

# =============================================================
# ▶️ INÍCIO DO SCRIPT
# =============================================================
if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("\n❗ Configure as variáveis de ambiente EMAIL e PASSWORD ou defina-as diretamente no código.")
    else:
        run_guardian()
