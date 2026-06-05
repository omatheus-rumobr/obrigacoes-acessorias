import json
import os
from pathlib import Path
import time

from dotenv import load_dotenv
import undetected_chromedriver as uc


WAIT_SECONDS = 40
COOKIES_PATH = Path("temp") / "cookies.json"


def main() -> None:
    load_dotenv()
    url = os.environ.get("TARGET_URL")
    if not url:
        raise SystemExit('Defina TARGET_URL no ambiente (ou no arquivo ".env").')

    COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)

    options = uc.ChromeOptions()
    driver = uc.Chrome(options=options, version_main=147)

    try:
        driver.get(url)
        time.sleep(WAIT_SECONDS)

        cookies = driver.get_cookies()
        COOKIES_PATH.write_text(
            json.dumps(cookies, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"Erro ao obter cookies: ")
        raise
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
