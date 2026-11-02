"""Run the QUANTUM AI Telegram bot."""
import logging
import os
from dotenv import load_dotenv
from app.telegram_bot import build_application

def main() -> None:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing. Set it as a private environment secret.")
    app = build_application(token)
    logging.info("Starting QUANTUM AI Telegram bot (informational mode; no trading).")
    app.run_polling(allowed_updates=["message"])

if __name__ == "__main__":
    main()
