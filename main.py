import logging

from database import init_db
from telegram_bot import build_application


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# Hindari mencetak URL request Telegram yang mengandung bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)


def main():
    print("Starting BlockWatcher...")

    init_db()
    print("Database initialized.")

    app = build_application()

    print("BlockWatcher Telegram bot is starting...")

    app.run_polling(
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()