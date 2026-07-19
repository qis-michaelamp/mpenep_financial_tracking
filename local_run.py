"""
Script buat TESTING LOKAL SAJA — pakai mode polling, bukan webhook.
Ini BUKAN yang dipakai di production (Vercel pakai webhook lewat api/webhook.py).

Kenapa bisa reuse semua logic yang sama: script ini cuma "jembatan" yang
manggil handle_update() persis kayak yang dipanggil webhook.py, cuma
sumber Update-nya beda (polling vs push).

Cara pakai:
  1. pip install -r requirements.txt
  2. pip install python-dotenv  (buat load .env.local, gak perlu di production)
  3. Copy .env.example jadi .env.local, isi semua value asli
  4. python local_run.py
  5. Chat bot lo di Telegram, seharusnya langsung kebales real-time
  6. Ctrl+C buat stop
"""

import os

from dotenv import load_dotenv

load_dotenv(".env.local")

from telegram import Update
from telegram.ext import Application, ContextTypes, TypeHandler

from bot.handlers import handle_update

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]


async def dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await handle_update(update, context.bot)


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    # TypeHandler(Update, ...) -> tangkep SEMUA jenis update (message & callback_query),
    # biar handle_update() yang urus routing-nya sendiri, sama persis kayak di webhook.py
    app.add_handler(TypeHandler(Update, dispatch))

    print("Bot jalan (polling mode). Coba chat di Telegram sekarang. Ctrl+C buat stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
