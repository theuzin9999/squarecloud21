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
LINK_AVIATOR = "https://www.goathbet.com/game/spribe-aviator"

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

POLLING_INTERVAL = 0.1          # ⚡ Turbo: Intervalo de checagem (0.1 segundo)
INTERVALO_MINIMO_ENVIO = 0.1    # ⚡ Turbo: Mínimo de tempo entre dois envios (segundos)
TEMPO_MAX_INATIVIDADE = 360     # 6 minutos (360 segundos)
TZ_BR = pytz.timezone("America/Sao_Paulo")

# =============================================================
# 🔧 FUNÇÕES AUXILIARES
# =============================================================
def getColorClass(value):
    """Retorna a cor conforme o multiplicador."""
    m = float(value)
    if 1.0 <= m < 2.0:
        return "blue-bg"
    if 2.0 <= m < 10.0:
        return "purple-bg"
    if m >= 10.0:
        return "magenta-bg"
    return "default-bg"

def safe_click(driver, by, value, timeout=5):
    """Tenta clicar em um elemento de forma segura."""
    try:
        # Usa execute_script para clicar, mais robusto em headless
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        driver.execute_script("arguments[0].click();", el)
        return True
    except Exception:
        return False

def safe_find(driver, by, value, timeout=5):
    """Tenta encontrar um elemento de forma segura."""
    try:
        return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))
    except Exception:
        return None

def initialize_game_elements(driver):
    """
    Localiza iframe e histórico do Aviator com prioridade atualizada.
    Os logs detalhados (Iframe encontrado) aparecem apenas aqui.
    """
    # 🎯 Prioridade 1: spribe (novo do site)
    POSSIVEIS_IFRAMES = [
        '//iframe[contains(@src, "spribe")]',
        '//iframe[contains(translate(@src,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"salsagator")]',
        '//iframe[contains(translate(@src,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"game?token")]',
        '//iframe[contains(@src, "/aviator/")]',
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
    for xpath in POSSIVEIS_IFRAMES:
        try:
            driver.switch_to.default_content()
            iframe = WebDriverWait(driver, 7).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            driver.switch_to.frame(iframe)
            print(f"✅ Iframe encontrado com XPath: {xpath}")
            break
        except Exception:
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
# 🔑 FLUXO DE LOGIN E NAVEGAÇÃO
# =============================================================
def process_login(driver):
    """Executa o fluxo de login e navegação para o Aviator."""
    if not EMAIL or not PASSWORD:
        print("❌ ERRO: EMAIL ou PASSWORD não configurados.")
        return False

    print("➡️ Executando login automático...")

    driver.get(URL_DO_SITE)
    sleep(2)

    # 1. Confirma maior de 18 (Busca o botão 'Sim')
    xpath_18 = "//button[contains(., 'Sim')]"
    if safe_click(driver, By.XPATH, xpath_18, 5) or \
       safe_click(driver, By.CSS_SELECTOR, 'button[data-age-action="yes"]', 5):
        print("✅ Confirmado maior de 18.")
        sleep(1)

    # 2. Abre janela de login (CSS Selector atualizado para ser mais robusto)
    if not safe_click(driver, By.CSS_SELECTOR, 'button[aria-label="Entrar"]', 5) and \
       not safe_click(driver, By.XPATH, "//button[contains(., 'Entrar')]", 5):
        print("❌ Botão 'Entrar' inicial não encontrado (Pode já estar logado).")
    sleep(1)

    # 3. Preenche e-mail e senha (por name ou id)
    try:
        email_input = safe_find(driver, By.NAME, "email", 3) or safe_find(driver, By.ID, "field-15", 3)
        pass_input = safe_find(driver, By.NAME, "password", 3) or safe_find(driver, By.ID, "password-login", 3)
        
        if email_input and pass_input:
            email_input.clear()
            email_input.send_keys(EMAIL)
            pass_input.clear()
            pass_input.send_keys(PASSWORD)
            sleep(0.5)

            # 4. Clica no botão final de login (Submissão)
            if safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 5) or \
               safe_click(driver, By.CSS_SELECTOR, "a[login-btn]", 5):
                print("✅ Credenciais preenchidas e login confirmado.")
                sleep(5)
            else:
                print("❌ Botão final de login não encontrado.")
                # Continua, caso já tenha sido logado automaticamente
        else:
            print("⚠️ Campos de login não encontrados. Pulando login manual.")
    except Exception as e:
        print(f"⚠️ Erro durante preenchimento do login: {e}")

    # 5. Aceita cookies
    safe_click(driver, By.XPATH, "//button[contains(., 'Aceitar')]", 4)
    print("✅ Cookies aceitos (se aplicável).")
    sleep(1)

    # 6. Abre Aviator
    driver.get(LINK_AVIATOR)
    print("ℹ️ Indo direto para o Aviator via link.")
    # Aguarda o jogo carregar
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe")]'))
        )
    except:
        sleep(3) # Fallback
    
    return True

def start_driver():
    """
    Inicializa o driver do Chrome.
    Adaptado para servidor sem interface gráfica (Square Cloud).
    """
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--headless")  # Roda sem interface gráfica
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")
    options.add_experimental_option('excludeSwitches', ['enable-logging'])

    # Em hospedagens baseadas em Debian/Ubuntu, usa-se este caminho
    # Se der erro, verifique se o ChromeDriver está instalado corretamente.
    service = Service("/usr/lib/chromium-browser/chromedriver") 

    return webdriver.Chrome(service=service, options=options)

# =============================================================
# 🚀 LOOP PRINCIPAL (TURBO OTIMIZADO)
# =============================================================
def start_bot(relogin_done_for: date = None):
    print("\n==============================================")
    print("  GOATHBOT V4.3 (ONLINE TURBO PRIORIZADO)")
    print("==============================================")

    driver = None
    try:
        driver = start_driver()

        # === FLUXO DE INICIALIZAÇÃO ===
        def setup_game(driver):
            if not process_login(driver):
                return None, None
            return initialize_game_elements(driver)

        iframe, hist = setup_game(driver)

        if not hist:
            print("❌ Falha crítica: Elementos do jogo não encontrados na inicialização. Reiniciando...")
            driver.quit()
            return start_bot()

        LAST_SENT = None
        ULTIMO_ENVIO = time()
        ULTIMO_MULTIPLIER_TIME = time()
        
        print("✅ Captura TURBO iniciada (foco no iframe para velocidade).\n")

        while True:
            # === VERIFICAÇÕES DE GUARDIÃO ===
            now_br = datetime.now(TZ_BR)
            
            # Reinício Diário
            if now_br.hour == 0 and now_br.minute <= 5 and (relogin_done_for != now_br.date()):
                print(f"🕛 REINÍCIO PROGRAMADO: {now_br.strftime('%H:%M:%S')}. Reiniciando...")
                driver.quit()
                return start_bot(relogin_done_for=now_br.date())

            # Inatividade
            if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                print(f"🚨 Inatividade por mais de 6 minutos. Reiniciando...")
                driver.quit()
                return start_bot()

            # === RECONEXÃO COM IFRAME E LEITURA ===
            try:
                # 1. Tenta manter o foco no iframe para leitura
                driver.switch_to.frame(iframe) 

                # 2. Leitura Rápida
                resultados = []
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
                    # Remove duplicatas, preservando ordem
                    seen = set()
                    resultados_unique = [x for x in resultados if not (x in seen or seen.add(x))]
                    
                    if resultados_unique:
                        novo = resultados_unique[0]
                        
                        if novo != LAST_SENT:
                            
                            if (time() - ULTIMO_ENVIO) > INTERVALO_MINIMO_ENVIO:

                                now_br = datetime.now(TZ_BR)
                                raw = f"{novo:.2f}"
                                entry_key = now_br.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                                time_display = now_br.strftime("%H:%M:%S")
                                color = getColorClass(novo)

                                entry = {"multiplier": raw, "time": time_display, "color": color, "date": now_br.strftime("%Y-%m-%d")}

                                try:
                                    # SALVA APENAS
                                    db.reference(f"history/{entry_key}").set(entry)
                                    print(f"🔥 {raw}x salvo às {time_display}")
                                except Exception as e:
                                    print("⚠️ Erro ao salvar:", e)

                                LAST_SENT = novo
                                ULTIMO_ENVIO = time()
                                ULTIMO_MULTIPLIER_TIME = time()  # Reseta o timer de inatividade

            except (StaleElementReferenceException, TimeoutException, WebDriverException):
                # Ocorre quando o iframe é recarregado ou a conexão cai
                print("⚠️ Conexão perdida com Iframe/Histórico. Reconectando elementos...")
                driver.switch_to.default_content() # Volta para o documento principal
                iframe, hist = initialize_game_elements(driver)
                if not hist: 
                    raise Exception("Falha na reconexão") # Joga para o guardian loop reiniciar

            # Não faz switch_to.default_content() aqui para manter o foco no iframe e ganhar velocidade
            sleep(POLLING_INTERVAL)

        return None # Nunca alcançado

    except KeyboardInterrupt:
        print("\n🛑 Bot parado manualmente.")
        if driver: driver.quit()
        return None
    
    except Exception as e:
        print(f"❌ Erro na sessão: {e}. Reiniciando...")
        if driver:
            try: driver.quit()
            except: pass
        return start_bot(relogin_done_for=relogin_done_for)

# =============================================================
# ▶️ INÍCIO DO SCRIPT
# =============================================================
if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("\n❗ Configure as variáveis de ambiente EMAIL e PASSWORD ou defina-as diretamente no código.")
    else:
        start_bot(relogin_done_for=date.today())
