import os
import sys
import pytz
import logging
import threading
import gc
import requests
import subprocess
import traceback
from time import sleep, time
from datetime import datetime

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

# 🔥 NOVA BIBLIOTECA DE CAMUFLAGEM
import undetected_chromedriver as uc
from selenium_stealth import stealth

import firebase_admin
from firebase_admin import credentials, db

# =============================================================
# ⚠️ CONTROLE GLOBAL DE THREADS E DRIVER
# =============================================================
[span_2](start_span)DRIVER_LOCK = threading.Lock()[span_2](end_span)
[span_3](start_span)STOP_EVENT = threading.Event()[span_3](end_span)

# =============================================================
# 🔥 CONFIGURAÇÃO FIREBASE
# =============================================================
[span_4](start_span)SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'[span_4](end_span)
# Substitua pela sua URL real do Firebase
[span_5](start_span)DATABASE_URL = 'https://your-database.firebaseio.com'[span_5](end_span)

try:
    [span_6](start_span)if not firebase_admin._apps:[span_6](end_span)
        [span_7](start_span)cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)[span_7](end_span)
        [span_8](start_span)firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})[span_8](end_span)
    [span_9](start_span)print("✅ Firebase Admin SDK inicializado.")[span_9](end_span)
except Exception as e:
    [span_10](start_span)print(f"\n❌ ERRO CONEXÃO FIREBASE: {e}")[span_10](end_span)
    [span_11](start_span)sys.exit()[span_11](end_span)

# =============================================================
# ⚙️ VARIÁVEIS 
# =============================================================
# Substitua pelos seus links reais
[span_12](start_span)URL_DO_SITE = "https://www.example.com"[span_12](end_span)
[span_13](start_span)LINK_AVIATOR_ORIGINAL = "https://www.example.com/pt/casino/spribe/aviator"[span_13](end_span)
[span_14](start_span)LINK_AVIATOR_2 = "https://www.example.com/casino/spribe/aviator-vip"[span_14](end_span)

[span_15](start_span)FIREBASE_PATH_ORIGINAL = "history"[span_15](end_span)
[span_16](start_span)FIREBASE_PATH_2 = "aviator2"[span_16](end_span)

[span_17](start_span)EMAIL = os.getenv("EMAIL")[span_17](end_span)
[span_18](start_span)PASSWORD = os.getenv("PASSWORD")[span_18](end_span)

[span_19](start_span)POLLING_INTERVAL = 1.0[span_19](end_span)
[span_20](start_span)TEMPO_MAX_INATIVIDADE = 360[span_20](end_span)
[span_21](start_span)TZ_BR = pytz.timezone("America/Sao_Paulo")[span_21](end_span)

# =============================================================
# 🔧 FUNÇÕES AUXILIARES
# =============================================================
def run_diagnostics():
    [span_22](start_span)print("\n--- 🕵️ DIAGNÓSTICO DE CONEXÃO ---")[span_22](end_span)
    try:
        [span_23](start_span)ip = requests.get('https://api.ipify.org', timeout=10).text[span_23](end_span)
        [span_24](start_span)print(f"🌐 IP Público: {ip}")[span_24](end_span)
        [span_25](start_span)res = requests.get(URL_DO_SITE, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})[span_25](end_span)
        [span_26](start_span)print(f"📡 Status Site (Requests normal): {res.status_code}")[span_26](end_span)
    except Exception as e:
        [span_27](start_span)print(f"⚠️ Alerta de Rede: {e}")[span_27](end_span)
    [span_28](start_span)print("----------------------------------\n")[span_28](end_span)

def getColorClass(value):
    try:
        [span_29](start_span)m = float(value)[span_29](end_span)
        [span_30](start_span)if 1.0 <= m < 2.0: return "blue-bg"[span_30](end_span)
        [span_31](start_span)if 2.0 <= m < 10.0: return "purple-bg"[span_31](end_span)
        [span_32](start_span)if m >= 10.0: return "magenta-bg"[span_32](end_span)
        [span_33](start_span)return "default-bg"[span_33](end_span)
    [span_34](start_span)except: return "default-bg"[span_34](end_span)

def enviar_firebase_async(path, data):
    def _send():
        try:
            [span_35](start_span)db.reference(path).set(data)[span_35](end_span)
            [span_36](start_span)nome_jogo = path.split('/')[0].upper()[span_36](end_span)
            [span_37](start_span)if nome_jogo == "HISTORY": nome_jogo = "AVIATOR 1"[span_37](end_span)
            [span_38](start_span)print(f"🔥 {nome_jogo}: {data['multiplier']}x às {data['time']}")[span_38](end_span)
        except Exception:
            pass 
    [span_39](start_span)threading.Thread(target=_send, daemon=True).start()[span_39](end_span)

def verificar_modais_bloqueio(driver):
    try:
        [span_40](start_span)btn_18 = WebDriverWait(driver, 3).until([span_40](end_span)
            [span_41](start_span)EC.element_to_be_clickable((By.XPATH, "//span[contains(., 'Sim, sou maior de 18')]"))[span_41](end_span)
        )
        [span_42](start_span)btn_18.click()[span_42](end_span)
        [span_43](start_span)sleep(0.5)[span_43](end_span)
        [span_44](start_span)print("✅ Modal 'Maior de 18' fechado.")[span_44](end_span)
    [span_45](start_span)except: pass[span_45](end_span)

    try:
        [span_46](start_span)xpath_btn_fechar = "//button[@data-slot='dialog-close' and contains(@class, 'modal-close')]"[span_46](end_span)
        [span_47](start_span)btn_fechar_cadastro = WebDriverWait(driver, 3).until([span_47](end_span)
            [span_48](start_span)EC.element_to_be_clickable((By.XPATH, xpath_btn_fechar))[span_48](end_span)
        )
        [span_49](start_span)btn_fechar_cadastro.click()[span_49](end_span)
        [span_50](start_span)sleep(1.5)[span_50](end_span)
        [span_51](start_span)print("✅ Modal 'Novo Cadastro' fechado.")[span_51](end_span)
    except: pass

    [span_52](start_span)botoes = ["//button[contains(., 'Sim')]", "//button[contains(., 'Aceitar')]", "//button[contains(., 'Fechar')]"][span_52](end_span)
    [span_53](start_span)for xpath in botoes:[span_53](end_span)
        try:
            [span_54](start_span)btn = driver.find_element(By.XPATH, xpath)[span_54](end_span)
            [span_55](start_span)if btn.is_displayed():[span_55](end_span)
                [span_56](start_span)btn.click()[span_56](end_span)
                [span_57](start_span)sleep(0.5)[span_57](end_span)
        except: pass

def stealth_script_inject(driver):
    """Injeta script adicional para mascarar o Selenium"""
    stealth_js = """
    [span_58](start_span)Object.defineProperty(navigator, 'webdriver', {[span_58](end_span)
      [span_59](start_span)get: () => false,[span_59](end_span)
    [span_60](start_span)});[span_60](end_span)
    [span_61](start_span)"""[span_61](end_span)
    try:
        [span_62](start_span)driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {[span_62](end_span)
            [span_63](start_span)'source': stealth_js[span_63](end_span)
        [span_64](start_span)})[span_64](end_span)
    except Exception as e:
        [span_65](start_span)print(f"Aviso ao injetar stealth script: {e}")[span_65](end_span)

# =============================================================
# 🚀 DRIVER COM UNDETECTED-CHROMEDRIVER
# =============================================================
def initialize_driver_instance():
    try:
        [span_66](start_span)if os.name == 'nt':[span_66](end_span)
            [span_67](start_span)subprocess.run("taskkill /f /im chromedriver.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)[span_67](end_span)
            [span_68](start_span)subprocess.run("taskkill /f /im chrome.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)[span_68](end_span)
        else:
            [span_69](start_span)subprocess.run("killall -9 chromium-browser chromium chromedriver 2>/dev/null", shell=True)[span_69](end_span)
    except: pass

    [span_70](start_span)options = uc.ChromeOptions()[span_70](end_span)
    [span_71](start_span)options.page_load_strategy = 'eager'[span_71](end_span)
    
    # Obrigatório para servidores
    [span_72](start_span)options.add_argument("--headless=new")[span_72](end_span)
    [span_73](start_span)options.add_argument("--no-sandbox")[span_73](end_span)
    [span_74](start_span)options.add_argument("--disable-dev-shm-usage")[span_74](end_span)
    [span_75](start_span)options.add_argument("--disable-popup-blocking")[span_75](end_span)
    
    # ✅ Novas configurações de camuflagem
    [span_76](start_span)options.add_argument("--window-size=1920,1080")[span_76](end_span)
    [span_77](start_span)options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")[span_77](end_span)
    [span_78](start_span)options.add_argument("--disable-blink-features=AutomationControlled")[span_78](end_span)

    try:
        # Inicializa usando undetected_chromedriver especificando a versão do Chrome da Square Cloud (148)
        [span_79](start_span)[span_80](start_span)driver = uc.Chrome(options=options, version_main=148)[span_79](end_span)[span_80](end_span)
        
        # Mantendo o selenium-stealth como camada extra de proteção
        [span_81](start_span)stealth(driver,[span_81](end_span)
            [span_82](start_span)languages=["pt-BR", "pt"],[span_82](end_span)
            [span_83](start_span)vendor="Google Inc.",[span_83](end_span)
            platform="Win32", # Simula que estamos no Windows
            [span_84](start_span)webgl_vendor="Intel Inc.",[span_84](end_span)
            [span_85](start_span)renderer="Intel Iris OpenGL Engine",[span_85](end_span)
            [span_86](start_span)fix_hairline=True,[span_86](end_span)
        [span_87](start_span))
        return driver[span_87](end_span)
    except Exception as e:
        [span_88](start_span)print(f"⚠️ Erro ao instalar/iniciar driver: {e}")[span_88](end_span)
        [span_89](start_span)return None[span_89](end_span)

def setup_tabs(driver):
    [span_90](start_span)stealth_script_inject(driver) # ✅ Injeção de script CDP adicionada[span_90](end_span)
    
    [span_91](start_span)print("➡️ Acessando site e configurando abas com Anti-Detecção UC...")[span_91](end_span)
    try:
        [span_92](start_span)driver.get(URL_DO_SITE)[span_92](end_span)
        [span_93](start_span)sleep(10) # Aguarda validação do Cloudflare[span_93](end_span)
        [span_94](start_span)verificar_modais_bloqueio(driver)[span_94](end_span)

        [span_95](start_span)WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Entrar')]"))).click()[span_95](end_span)
        [span_96](start_span)sleep(2)[span_96](end_span)
        [span_97](start_span)driver.find_element(By.NAME, "email").send_keys(EMAIL)[span_97](end_span)
        [span_98](start_span)driver.find_element(By.NAME, "password").send_keys(PASSWORD)[span_98](end_span)
        [span_99](start_span)driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()[span_99](end_span)
        [span_100](start_span)print("✅ Login enviado.")[span_100](end_span)
        [span_101](start_span)sleep(10)[span_101](end_span)
    except Exception as e:
        [span_102](start_span)print(f"⚠️ Aviso no login: {e}")[span_102](end_span)

    [span_103](start_span)driver.get(LINK_AVIATOR_ORIGINAL)[span_103](end_span)
    [span_104](start_span)sleep(5)[span_104](end_span)
    [span_105](start_span)handle_original = driver.current_window_handle[span_105](end_span)
    [span_106](start_span)print(f"✅ Aba Aviator 1 configurada.")[span_106](end_span)

    [span_107](start_span)driver.execute_script("window.open('');")[span_107](end_span)
    [span_108](start_span)handles = driver.window_handles[span_108](end_span)
    [span_109](start_span)handle_aviator2 = [h for h in handles if h != handle_original][0][span_109](end_span)
    
    [span_110](start_span)driver.switch_to.window(handle_aviator2)[span_110](end_span)
    [span_111](start_span)driver.get(LINK_AVIATOR_2)[span_111](end_span)
    [span_112](start_span)sleep(5)[span_112](end_span)
    [span_113](start_span)print(f"✅ Aba Aviator 2 configurada.")[span_113](end_span)
    
    [span_114](start_span)driver.switch_to.window(handle_original)[span_114](end_span)
    [span_115](start_span)return {FIREBASE_PATH_ORIGINAL: handle_original, FIREBASE_PATH_2: handle_aviator2}[span_115](end_span)

# =============================================================
# 🎮 BUSCA DE ELEMENTOS
# =============================================================
def find_game_elements_safe(driver):
    try:
        [span_116](start_span)driver.implicitly_wait(2)[span_116](end_span)
        [span_117](start_span)iframe = driver.find_element(By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]')[span_117](end_span)
        [span_118](start_span)driver.switch_to.frame(iframe)[span_118](end_span)
        [span_119](start_span)hist = driver.find_element(By.CSS_SELECTOR, "app-stats-widget, .payouts-block")[span_119](end_span)
        [span_120](start_span)driver.implicitly_wait(10)[span_120](end_span)
        [span_121](start_span)return iframe, hist[span_121](end_span)
    except:
        [span_122](start_span)driver.implicitly_wait(10)[span_122](end_span)
        [span_123](start_span)return None, None[span_123](end_span)

# =============================================================
# 🔄 LOOP DE CAPTURA
# =============================================================
def start_bot(driver, game_handle, firebase_path):
    [span_124](start_span)nome_log = "AVIATOR 1" if "history" in firebase_path else "AVIATOR 2"[span_124](end_span)
    [span_125](start_span)print(f"🚀 INICIADO: {nome_log}")[span_125](end_span)
    
    [span_126](start_span)LAST_SENT = None[span_126](end_span)
    [span_127](start_span)ULTIMO_MULTIPLIER_TIME = time()[span_127](end_span)

    [span_128](start_span)while not STOP_EVENT.is_set():[span_128](end_span)
        [span_129](start_span)raw_text = None[span_129](end_span)
        [span_130](start_span)with DRIVER_LOCK:[span_130](end_span)
            [span_131](start_span)if STOP_EVENT.is_set(): break[span_131](end_span)
            try:
                [span_132](start_span)driver.switch_to.window(game_handle)[span_132](end_span)
                [span_133](start_span)driver.switch_to.default_content()[span_133](end_span)
                [span_134](start_span)iframe, hist_element = find_game_elements_safe(driver)[span_134](end_span)
                
                [span_135](start_span)if hist_element:[span_135](end_span)
                    [span_136](start_span)first_payout = hist_element.find_element([span_136](end_span)
                        [span_137](start_span)By.CSS_SELECTOR,[span_137](end_span)
                        [span_138](start_span)"[appcoloredmultiplier].payout:first-child, .payout:first-child, .bubble-multiplier:first-child"[span_138](end_span)
                    [span_139](start_span))
                    raw_text = first_payout.get_attribute("innerText")[span_139](end_span)
            except: pass

        [span_140](start_span)if raw_text:[span_140](end_span)
            [span_141](start_span)clean_text = raw_text.strip().lower().replace('x', '').replace('\n', '').strip()[span_141](end_span)
            [span_142](start_span)if clean_text:[span_142](end_span)
                try:
                    [span_143](start_span)novo_valor = float(clean_text)[span_143](end_span)
                    [span_144](start_span)if novo_valor != LAST_SENT:[span_144](end_span)
                        [span_145](start_span)now_br = datetime.now(TZ_BR)[span_145](end_span)
                        [span_146](start_span)payload = {[span_146](end_span)
                            [span_147](start_span)"multiplier": f"{novo_valor:.2f}",[span_147](end_span)
                            [span_148](start_span)"time": now_br.strftime("%H:%M:%S"),[span_148](end_span)
                            [span_149](start_span)"color": getColorClass(novo_valor),[span_149](end_span)
                            [span_150](start_span)"date": now_br.strftime("%Y-%m-%d")[span_150](end_span)
                        [span_151](start_span)}
                        chave_firebase = now_br.strftime('%Y-%m-%d_%H-%M-%S-%f')[:-3][span_151](end_span)
                        [span_152](start_span)enviar_firebase_async(f"{firebase_path}/{chave_firebase}", payload)[span_152](end_span)
                        
                        [span_153](start_span)LAST_SENT = novo_valor[span_153](end_span)
                        [span_154](start_span)ULTIMO_MULTIPLIER_TIME = time()[span_154](end_span)
                except: pass 

        [span_155](start_span)if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:[span_155](end_span)
            [span_156](start_span)print(f"⚠️ [{nome_log}] Sem dados por mais de {TEMPO_MAX_INATIVIDADE}s. Reiniciando...")[span_156](end_span)
            [span_157](start_span)STOP_EVENT.set()[span_157](end_span)
            return 
            
        [span_158](start_span)sleep(POLLING_INTERVAL)[span_158](end_span)

# =============================================================
# 🚀 SUPERVISOR (MAIN LOOP)
# =============================================================
def rodar_ciclo_monitoramento():
    [span_159](start_span)DRIVER = None[span_159](end_span)
    [span_160](start_span)STOP_EVENT.clear()[span_160](end_span)
    
    try:
        [span_161](start_span)print("\n🔵 INICIANDO NOVO CICLO COM UNDETECTED-CHROMEDRIVER...")[span_161](end_span)
        [span_162](start_span)DRIVER = initialize_driver_instance()[span_162](end_span)
        
        [span_163](start_span)if not DRIVER:[span_163](end_span)
            [span_164](start_span)print("⚠️ Falha ao instanciar o driver. Aguardando para nova tentativa...")[span_164](end_span)
            [span_165](start_span)sleep(10)[span_165](end_span)
            return

        [span_166](start_span)handles = setup_tabs(DRIVER)[span_166](end_span)
        
        [span_167](start_span)handle_original = handles[FIREBASE_PATH_ORIGINAL][span_167](end_span)
        [span_168](start_span)handle_aviator2 = handles[FIREBASE_PATH_2][span_168](end_span)

        [span_169](start_span)print("⏳ Monitoramento iniciado (Threads)...")[span_169](end_span)
        
        [span_170](start_span)t1 = threading.Thread(target=start_bot, args=(DRIVER, handle_original, FIREBASE_PATH_ORIGINAL), daemon=True)[span_170](end_span)
        [span_171](start_span)t2 = threading.Thread(target=start_bot, args=(DRIVER, handle_aviator2, FIREBASE_PATH_2), daemon=True)[span_171](end_span)

        [span_172](start_span)t1.start()[span_172](end_span)
        [span_173](start_span)t2.start()[span_173](end_span)

        [span_174](start_span)while t1.is_alive() or t2.is_alive():[span_174](end_span)
            [span_175](start_span)if STOP_EVENT.is_set():[span_175](end_span)
                [span_176](start_span)break[span_176](end_span)
            [span_177](start_span)sleep(2)[span_177](end_span)
            
        [span_178](start_span)print("🛑 Ciclo encerrado. Limpando recursos...")[span_178](end_span)
        
    except Exception as e:
        [span_179](start_span)print(f"\n❌ ERRO NO CICLO: {e}")[span_179](end_span)
        [span_180](start_span)traceback.print_exc()[span_180](end_span)
    finally:
        [span_181](start_span)STOP_EVENT.set()[span_181](end_span)
        [span_182](start_span)if DRIVER:[span_182](end_span)
            try:
                [span_183](start_span)DRIVER.quit()[span_183](end_span)
                [span_184](start_span)print("🗑️ Driver encerrado com sucesso.")[span_184](end_span)
            except: pass
        [span_185](start_span)gc.collect()[span_185](end_span)
        [span_186](start_span)sleep(5)[span_186](end_span)

if __name__ == "__main__":
    [s
