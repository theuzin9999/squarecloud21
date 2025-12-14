# bot_secure_relogin_improved.py
from __future__ import annotations

import os
import sys
import logging
import threading
import signal
from dataclasses import dataclass
from time import sleep, time
from datetime import datetime, date
from typing import Optional, Tuple, List

import pytz
import firebase_admin
from firebase_admin import credentials, db

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)

from webdriver_manager.chrome import ChromeDriverManager


# =============================================================
# CONFIG
# =============================================================
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "serviceAccountKey.json")
DATABASE_URL = os.getenv(
    "DATABASE_URL", "https://history-dashboard-a70ee-default-rtdb.firebaseio.com"
)
URL_DO_SITE = os.getenv("URL_DO_SITE", "https://www.goathbet.com")

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

TZ_BR = pytz.timezone(os.getenv("TZ", "America/Sao_Paulo"))

# Performance / estabilidade
POLLING_INTERVAL = float(os.getenv("POLLING_INTERVAL", "0.12"))  # ~8Hz default
TEMPO_MAX_INATIVIDADE = int(os.getenv("TEMPO_MAX_INATIVIDADE", "360"))  # segundos

# Reinício diário (janela em minutos após 00:00)
DAILY_RESTART_WINDOW_MIN = int(os.getenv("DAILY_RESTART_WINDOW_MIN", "7"))

# Comparação float com tolerância
FLOAT_EPS = float(os.getenv("FLOAT_EPS", "0.0001"))

# Headless
HEADLESS = os.getenv("HEADLESS", "1").strip() != "0"

# Chrome driver path opcional (ex: /usr/bin/chromedriver)
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH")

# =============================================================
# LOGGING
# =============================================================
logging.getLogger("WDM").setLevel(logging.ERROR)
os.environ["WDM_LOG_LEVEL"] = "0"

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper().strip()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("goathbot")

# =============================================================
# MULTI-BOTS
# =============================================================
CONFIG_BOTS = [
    {
        "nome": "ORIGINAL",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator",
        "firebase_path": "history",
    },
    {
        "nome": "AVIATOR 2",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator-2",
        "firebase_path": "aviator2",
    },
]


# =============================================================
# GLOBAL STOP (shutdown limpo)
# =============================================================
STOP_EVENT = threading.Event()


def _handle_signal(sig, frame):
    STOP_EVENT.set()
    log.warning("Recebido sinal %s. Encerrando...", sig)


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# =============================================================
# FIREBASE INIT (1x)
# =============================================================
def init_firebase() -> None:
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
            firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})
        log.info("Firebase: conectado.")
    except Exception as e:
        log.error("FIREBASE: erro crítico: %s", e)
        # Se firebase falhar, não adianta continuar.
        raise


# =============================================================
# SELENIUM HELPERS
# =============================================================
def start_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    if HEADLESS:
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.page_load_strategy = "eager"
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--log-level=3")
    options.add_argument("--silent")

    try:
        if CHROMEDRIVER_PATH and os.path.exists(CHROMEDRIVER_PATH):
            return webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=options)
        return webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=options
        )
    except Exception:
        # Fallback comum em Linux
        return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)


def safe_click(driver: webdriver.Chrome, by: By, value: str, timeout: int = 5) -> bool:
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((by, value))
        )
        driver.execute_script("arguments[0].click();", element)
        return True
    except Exception:
        return False


def check_blocking_modals(driver: webdriver.Chrome) -> None:
    # fecha modais comuns
    xpaths = [
        "//button[contains(., 'Sim')]",
        "//button[@data-age-action='yes']",
        "//div[contains(text(), '18')]/following::button[1]",
        "//button[contains(., 'Aceitar')]",
        "//button[contains(., 'Entendi')]",
        "//button[contains(., 'OK')]",
    ]
    for xp in xpaths:
        if STOP_EVENT.is_set():
            return
        if safe_click(driver, By.XPATH, xp, timeout=1):
            break


def wait_for_iframe(driver: webdriver.Chrome, timeout: int = 15):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located(
            (By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]')
        )
    )


def wait_for_history_element(driver: webdriver.Chrome, timeout: int = 8):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block, app-stats-widget"))
    )


def process_login(driver: webdriver.Chrome, target_link: str) -> None:
    # abre home
    try:
        driver.get(URL_DO_SITE)
    except WebDriverException:
        pass

    sleep(2)
    check_blocking_modals(driver)

    # abre login
    opened = safe_click(driver, By.XPATH, "//button[contains(., 'Entrar')]", 6) or safe_click(
        driver, By.CSS_SELECTOR, 'a[href*="login"]', 6
    )

    if opened:
        sleep(1)
        try:
            email_el = WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.NAME, "email"))
            )
            pass_el = driver.find_element(By.NAME, "password")
            email_el.clear()
            pass_el.clear()
            email_el.send_keys(EMAIL or "")
            pass_el.send_keys(PASSWORD or "")
            safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 6)
            sleep(3)
        except Exception:
            # Mesmo se falhar, tenta abrir o jogo direto (às vezes já está logado)
            pass

    # abre jogo
    driver.get(target_link)
    try:
        wait_for_iframe(driver, timeout=18)
    except Exception:
        pass
    check_blocking_modals(driver)


def initialize_game_elements(
    driver: webdriver.Chrome,
) -> Tuple[Optional[object], Optional[object]]:
    # retorna (iframe, history_element) ou (None, None)
    try:
        driver.switch_to.default_content()
    except Exception:
        pass

    try:
        iframe = wait_for_iframe(driver, timeout=12)
        driver.switch_to.frame(iframe)
    except Exception:
        return None, None

    try:
        hist = wait_for_history_element(driver, timeout=10)
        return iframe, hist
    except Exception:
        return None, None


def get_color_class(m: float) -> str:
    if 1.0 <= m < 2.0:
        return "blue-bg"
    if 2.0 <= m < 10.0:
        return "purple-bg"
    if m >= 10.0:
        return "magenta-bg"
    return "default-bg"


def floats_equal(a: float, b: float, eps: float = FLOAT_EPS) -> bool:
    return abs(a - b) <= eps


def parse_multipliers(hist) -> List[float]:
    """
    Tenta extrair multiplicadores do histórico.
    Primeiro pelos itens individuais; se falhar, fallback pelo texto bruto.
    Retorna lista com o mais recente primeiro (como no seu bot original).
    """
    resultados: List[float] = []

    # 1) itens
    try:
        items = hist.find_elements(By.CSS_SELECTOR, ".payout, .bubble-multiplier")
        for it in items:
            txt = (it.get_attribute("innerText") or "").strip().replace("x", "")
            if not txt:
                continue
            try:
                v = float(txt)
                if v >= 1.0:
                    resultados.append(v)
            except ValueError:
                continue
    except Exception:
        pass

    # 2) fallback texto bruto
    if not resultados:
        try:
            txt_full = (hist.get_attribute("innerText") or "")
            txt_full = txt_full.replace("x", " ").replace("\n", " ")
            for val in txt_full.split():
                try:
                    v = float(val)
                    if v >= 1.0:
                        resultados.append(v)
                except ValueError:
                    continue
        except Exception:
            pass

    return resultados


@dataclass
class BotConfig:
    nome: str
    link: str
    firebase_path: str


def run_single_bot(cfg: BotConfig) -> None:
    nome = cfg.nome
    link = cfg.link
    path_fb = cfg.firebase_path

    relogin_date = date.today()

    while not STOP_EVENT.is_set():
        driver: Optional[webdriver.Chrome] = None
        try:
            log.info("[%s] Driver iniciando...", nome)
            driver = start_driver()

            process_login(driver, link)

            iframe, hist = initialize_game_elements(driver)
            if not hist:
                raise RuntimeError("Elementos do jogo não encontrados (hist).")

            log.info("[%s] Monitorando Firebase em '%s'", nome, path_fb)

            last_sent: Optional[float] = None
            last_seen_time = time()

            while not STOP_EVENT.is_set():
                now_br = datetime.now(TZ_BR)

                # 1) Reinício diário (janela após 00:00)
                if (
                    now_br.hour == 0
                    and now_br.minute <= DAILY_RESTART_WINDOW_MIN
                    and relogin_date != now_br.date()
                ):
                    log.info("[%s] Reinício diário acionado.", nome)
                    relogin_date = now_br.date()
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    break  # reinicia o driver (loop externo)

                # 2) Inatividade
                if (time() - last_seen_time) > TEMPO_MAX_INATIVIDADE:
                    raise RuntimeError("Inatividade detectada (sem multipliers novos).")

                # 3) Leitura + envio
                try:
                    resultados = parse_multipliers(hist)

                    if resultados:
                        novo = resultados[0]

                        if (last_sent is None) or (not floats_equal(novo, last_sent)):
                            last_seen_time = time()

                            entry = {
                                "multiplier": f"{novo:.2f}",
                                "time": now_br.strftime("%H:%M:%S"),
                                "color": get_color_class(novo),
                                "date": now_br.strftime("%Y-%m-%d"),
                            }

                            # chave única (evita colisão; ms + thread)
                            key = (
                                now_br.strftime("%Y-%m-%d_%H-%M-%S-%f")
                                + f"_{nome.replace(' ', '_')}"
                            )

                            try:
                                db.reference(f"{path_fb}/{key}").set(entry)
                                log.info("[%s] %s x", nome, entry["multiplier"])
                                last_sent = novo
                            except Exception as e:
                                log.warning("[%s] Firebase erro: %s", nome, e)

                    sleep(POLLING_INTERVAL)

                except (StaleElementReferenceException, TimeoutException):
                    # reanexa iframe/elementos
                    try:
                        driver.switch_to.default_content()
                    except Exception:
                        pass
                    iframe, hist = initialize_game_elements(driver)
                    if not hist:
                        raise RuntimeError("Perdeu conexão com elementos do jogo.")

        except Exception as e:
            log.error("[%s] Falha: %s", nome, e)
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

            # backoff curto
            for _ in range(10):
                if STOP_EVENT.is_set():
                    break
                sleep(0.5)

    # shutdown thread
    log.warning("[%s] Thread encerrada.", nome)


def main() -> int:
    if not EMAIL or not PASSWORD:
        log.error("Configure EMAIL e PASSWORD nas variáveis de ambiente.")
        return 2

    init_firebase()

    log.info("==============================================")
    log.info(" GOATHBOT - DUAL MONITORING (IMPROVED)")
    log.info(" Headless=%s | Polling=%.3fs | Inatividade=%ss",
             str(HEADLESS), POLLING_INTERVAL, TEMPO_MAX_INATIVIDADE)
    log.info("==============================================")

    threads: List[threading.Thread] = []

    for item in CONFIG_BOTS:
        cfg = BotConfig(
            nome=item["nome"],
            link=item["link"],
            firebase_path=item["firebase_path"],
        )
        t = threading.Thread(target=run_single_bot, args=(cfg,), daemon=True)
        t.start()
        threads.append(t)
        sleep(1.5)

    # mantém vivo até parar
    try:
        while not STOP_EVENT.is_set():
            sleep(0.5)
    finally:
        STOP_EVENT.set()
        for t in threads:
            t.join(timeout=10)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
