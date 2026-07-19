
"""
Entrypoint TUNGGAL buat Vercel (Vercel nyari file bernama app.py/index.py/main.py/dst
di /api, BUKAN lagi 'tiap .py otomatis jadi endpoint terpisah').
Semua route (webhook Telegram + cron reminder) digabung di sini dalam 1 Flask app.
"""

import asyncio
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, request
from telegram import Bot, Update

from bot import keyboards
from bot.handlers import handle_update
from bot.supabase_client import (
    credit_deposit_interest_rollover,
    get_deposits_near_maturity_all_families,
    get_deposits_with_monthly_interest_due_today_all_families,
    get_family_member_chat_ids,
    get_installments_due_today_all_families,
)

app = Flask(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
CRON_SECRET = os.environ.get("CRON_SECRET")
JAKARTA_TZ = ZoneInfo("Asia/Jakarta")


# ============================================
# WEBHOOK TELEGRAM
# ============================================

async def _process_update(data: dict) -> None:
    bot = Bot(token=BOT_TOKEN)
    async with bot:
        update = Update.de_json(data, bot)
        await handle_update(update, bot)


@app.route("/api/webhook", methods=["POST"])
def webhook():
    if WEBHOOK_SECRET:
        incoming = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if incoming != WEBHOOK_SECRET:
            return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status": "ignored"}), 200

    try:
        asyncio.run(_process_update(data))
    except Exception as e:
        print(f"Error processing update: {e}")

    return jsonify({"status": "ok"}), 200


@app.route("/api/webhook", methods=["GET"])
def webhook_health_check():
    return jsonify({"status": "bot is running"}), 200


# ============================================
# CRON REMINDER
# ============================================

async def _run_reminders() -> dict:
    bot = Bot(token=BOT_TOKEN)
    today = datetime.now(JAKARTA_TZ).date()
    current_month = today.strftime("%Y-%m")

    summary = {
        "installment_reminders": 0,
        "deposit_reminders": 0,
        "deposit_maturity": 0,
        "monthly_interest_rollover": 0,
        "monthly_interest_payout_reminders": 0,
    }

    async with bot:
        due_installments = get_installments_due_today_all_families(today.day, current_month)
        for inst in due_installments:
            chat_ids = get_family_member_chat_ids(inst.family_id)
            label = "KPR" if inst.obligation_type == "kpr" else "Cicilan Kartu Kredit"
            amount_str = f"Rp{inst.amount_per_month:,.0f}".replace(",", ".")
            text = f"💳 *{label} jatuh tempo hari ini*\n{inst.name}: {amount_str}"
            markup = keyboards.build_installment_reminder_keyboard(inst.id)
            for chat_id in chat_ids:
                try:
                    await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
                    summary["installment_reminders"] += 1
                except Exception as e:
                    print(f"Gagal kirim reminder cicilan ke {chat_id}: {e}")

        near_deposits = get_deposits_near_maturity_all_families(today, days_ahead=3)
        for dep in near_deposits:
            maturity = date.fromisoformat(dep.maturity_date)
            days_left = (maturity - today).days
            chat_ids = get_family_member_chat_ids(dep.family_id)
            principal_str = f"Rp{dep.principal_amount:,.0f}".replace(",", ".")

            if days_left <= 0:
                text = (
                    f"🏦 *Deposito jatuh tempo hari ini*\n{dep.name}: {principal_str}\n"
                    "Mau diperpanjang atau dicairkan?"
                )
                markup = keyboards.build_deposit_maturity_keyboard(dep.id)
                for chat_id in chat_ids:
                    try:
                        await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
                        summary["deposit_maturity"] += 1
                    except Exception as e:
                        print(f"Gagal kirim maturity deposito ke {chat_id}: {e}")
            elif not dep.reminder_dismissed:
                text = f"🏦 *Deposito jatuh tempo {days_left} hari lagi*\n{dep.name}: {principal_str}"
                markup = keyboards.build_deposit_dismiss_keyboard(dep.id)
                for chat_id in chat_ids:
                    try:
                        await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
                        summary["deposit_reminders"] += 1
                    except Exception as e:
                        print(f"Gagal kirim reminder deposito ke {chat_id}: {e}")

        monthly_deposits = get_deposits_with_monthly_interest_due_today_all_families(today.day, current_month)
        for dep in monthly_deposits:
            monthly_interest = dep.principal_amount * (dep.interest_rate_pct_pa / 100) / 12
            chat_ids = get_family_member_chat_ids(dep.family_id)
            interest_str = f"Rp{monthly_interest:,.0f}".replace(",", ".")

            if dep.interest_mode == "rollover":
                credit_deposit_interest_rollover(dep.id, monthly_interest, current_month)
                text = f"🔄 *Bunga {dep.name} bulan ini*\n{interest_str} otomatis masuk ke pokok."
                for chat_id in chat_ids:
                    try:
                        await bot.send_message(chat_id, text, parse_mode="Markdown")
                        summary["monthly_interest_rollover"] += 1
                    except Exception as e:
                        print(f"Gagal kirim notif rollover ke {chat_id}: {e}")
            elif dep.interest_mode == "payout":
                text = f"💰 *Bunga {dep.name} bulan ini*\n{interest_str}, cair ke akun?"
                markup = keyboards.build_interest_payout_confirm_keyboard(dep.id)
                for chat_id in chat_ids:
                    try:
                        await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
                        summary["monthly_interest_payout_reminders"] += 1
                    except Exception as e:
                        print(f"Gagal kirim reminder bunga payout ke {chat_id}: {e}")

    return summary


@app.route("/api/cron_reminder", methods=["GET", "POST"])
def cron_reminder():
    if CRON_SECRET:
        auth_header = request.headers.get("Authorization", "")
        if auth_header != f"Bearer {CRON_SECRET}":
            return jsonify({"error": "unauthorized"}), 401

    try:
        summary = asyncio.run(_run_reminders())
    except Exception as e:
        print(f"Cron error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "ok", "summary": summary}), 200


@app.route("/", methods=["GET"])
def root_health_check():
    return jsonify({"status": "keuangan-bot API is running"}), 200