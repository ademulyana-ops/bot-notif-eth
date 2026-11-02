
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = int(os.getenv("TELEGRAM_OWNER_ID", "0"))

ALCHEMY_HTTPS_URL = os.getenv("ALCHEMY_HTTPS_URL")
ALCHEMY_WSS_URL = os.getenv("ALCHEMY_WSS_URL")

NETWORK = os.getenv("NETWORK", "ethereum")

if not BOT_TOKEN:
    raise ValueError("Telegram Bot Token belum diatur")

if OWNER_ID == 0:
    raise ValueError("Telegram Owner ID belum diatur")

if not ALCHEMY_HTTPS_URL or not ALCHEMY_WSS_URL:
    raise ValueError("Alchemy URL belum diatur")
