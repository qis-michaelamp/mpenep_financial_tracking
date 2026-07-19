"""
Script SEKALI JALAN buat register command list ke Telegram (setMyCommands),
biar command muncul di menu saran pas user ketik "/" di chat.

Ini gak perlu dijalanin ulang tiap deploy -- command list tersimpan di sisi
Telegram, bukan di kode. Cuma perlu dijalanin ulang kalau ada command baru
ditambah/dihapus/diubah deskripsinya.

Cara pakai:
  1. pip install python-dotenv (kalau belum)
  2. Copy .env.example jadi .env.local, isi TELEGRAM_BOT_TOKEN
  3. python register_commands.py
"""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv(".env.local")

from telegram import Bot, BotCommand

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

COMMANDS = [
    BotCommand("saldo", "Lihat saldo semua akun"),
    BotCommand("riwayat", "Riwayat transaksi (default 10, maks 50)"),
    BotCommand("manajemenakun", "Tambah/hapus/lihat akun"),
    BotCommand("setmodal", "Atur/koreksi saldo awal akun"),
    BotCommand("tambahcicilan", "Daftar cicilan KK/KPR/langganan baru"),
    BotCommand("cicilan", "Lihat cicilan & langganan aktif"),
    BotCommand("updatebunga", "Update suku bunga KPR"),
    BotCommand("kartukredit", "Ringkasan utang & langganan per kartu"),
    BotCommand("tambahdeposito", "Daftar deposito baru"),
    BotCommand("deposito", "Lihat deposito aktif"),
    BotCommand("tambahaset", "Daftar aset baru (emas/valas/saham/lain)"),
    BotCommand("aset", "Lihat aset & estimasi gain/loss"),
    BotCommand("updateharga", "Update harga terkini aset"),
    BotCommand("dashboard", "Link dashboard rekap keuangan"),
    BotCommand("undang", "Undang anggota keluarga baru (admin)"),
    BotCommand("batal", "Batalin input yang lagi jalan"),
    BotCommand("help", "Tampilin daftar command"),
]


async def main() -> None:
    bot = Bot(BOT_TOKEN)
    await bot.set_my_commands(COMMANDS)
    print(f"Berhasil register {len(COMMANDS)} command ke Telegram.")


if __name__ == "__main__":
    asyncio.run(main())
