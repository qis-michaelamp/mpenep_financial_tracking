"""
Handler utama bot. Dipanggil dari api/webhook.py dengan 1 Update per invocation.

Alur:
  Text message  -> handle_message()   -> parse nominal, mulai/lanjut draft
  Callback query -> handle_callback() -> proses tap tombol, lanjutkan step

State disimpan di tabel bot_sessions (bukan memory Python), karena tiap
invocation di Vercel itu instance baru yang gak inget request sebelumnya.
"""

from datetime import date, timedelta
import calendar
import os

from telegram import Bot, Update
from telegram.error import BadRequest

from bot import keyboards
from bot.parser import parse_plain_amount, parse_transaction_text
from bot.supabase_client import (
    FamilyMember,
    clear_session,
    create_account,
    create_deposit,
    create_installment,
    create_pending_member,
    credit_deposit_interest_rollover,
    account_has_dependencies,
    create_asset,
    delete_account,
    get_account_balance,
    get_account_by_id,
    get_account_expense_this_month,
    get_accounts,
    get_active_deposits,
    get_active_installments,
    get_asset_by_name,
    get_assets,
    get_categories,
    get_category_by_id,
    get_deposit_by_id,
    get_installment_by_id,
    get_member_by_chat_id,
    get_member_by_invite_code,
    get_recent_transactions,
    get_session,
    insert_transaction,
    register_member_chat_id,
    rollover_deposit,
    save_session,
    update_account_initial_balance,
    update_asset_price,
    update_deposit_last_interest_month,
    update_installment_interest_rate,
    dismiss_deposit_reminder,
    increment_installment_months_paid,
    mark_installment_charged,
    update_deposit_status,
)

TYPE_LABELS = {"expense": "Expense", "income": "Income", "transfer": "Transfer"}
BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "")
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "")


_HARI_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
_BULAN_ID = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

# Batas /riwayat -> jaga query & panjang pesan tetap ringan meski user minta banyak
RIWAYAT_DEFAULT_LIMIT = 10
RIWAYAT_MAX_LIMIT = 50


def format_date_id(date_str: str) -> str:
    """"2026-07-19" -> "Sabtu, 19 Juli 2026" tanpa gantung ke locale sistem
    (locale Indonesia sering gak ke-install di runtime serverless)."""
    d = date.fromisoformat(date_str)
    return f"{_HARI_ID[d.weekday()]}, {d.day} {_BULAN_ID[d.month - 1]} {d.year}"


def format_rupiah(amount: float) -> str:
    """Format nominal ke Rupiah locale ID (titik ribuan, koma desimal).
    Desimal cuma dimunculin kalau nominalnya emang punya pecahan (misal dari
    input "8521.62") -> nominal bulat tetap tampil tanpa desimal kayak biasa."""
    is_whole = abs(amount - round(amount)) < 0.005
    raw = f"{amount:,.0f}" if is_whole else f"{amount:,.2f}"
    return "Rp" + raw.replace(",", "#").replace(".", ",").replace("#", ".")


def add_months(d: date, months: int) -> date:
    """Tambah N bulan ke tanggal, handle overflow hari (misal 31 Jan + 1 bulan -> 28/29 Feb)."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


async def safe_edit_message_text(callback_query, text, **kwargs) -> None:
    """
    Wrapper edit_message_text yang aman dari error Telegram
    'Message is not modified' -> ini muncul kalau user double-tap tombol
    atau konten yang mau di-edit persis sama kayak yang udah tampil.
    Bukan bug, jadi aman diabaikan.
    """
    try:
        await callback_query.edit_message_text(text, **kwargs)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise


async def handle_update(update: Update, bot: Bot) -> None:
    """Entry point dipanggil dari webhook.py"""
    if update.message and update.message.text:
        await handle_message(update.message, bot)
    elif update.callback_query:
        await handle_callback(update.callback_query, bot)


# ============================================
# TEXT MESSAGE
# ============================================

async def handle_message(message, bot: Bot) -> None:
    chat_id = message.chat_id
    text = message.text.strip()

    # /daftar KODE atau /start KODE (dari deep link t.me/bot?start=KODE) harus bisa
    # dipanggil orang yang BELUM terdaftar (justru itu tujuannya), jadi dicek
    # sebelum whitelist check di bawah.
    parts = text.split(maxsplit=1)
    command_word = parts[0].lower()
    has_arg = len(parts) > 1
    if command_word == "/daftar" or (command_word == "/start" and has_arg):
        await handle_register(text, chat_id, bot)
        return

    member = get_member_by_chat_id(chat_id)

    if member is None:
        await bot.send_message(
            chat_id,
            "Maaf, kamu belum terdaftar buat pakai bot ini. "
            "Minta admin keluarga buat generate kode undangan (/undang), "
            "terus daftar pakai `/daftar KODE`.",
            parse_mode="Markdown",
        )
        return

    if text.startswith("/"):
        await handle_command(text, chat_id, member, bot)
        return

    session = get_session(chat_id)

    # Kalau lagi nunggu input tanggal custom
    if session.get("awaiting") == "custom_date":
        await handle_custom_date_input(text, chat_id, member, session, bot)
        return

    # Kalau lagi nunggu input nominal buat set saldo awal (flow /setmodal)
    if session.get("flow") == "set_balance" and session.get("awaiting") == "balance_amount":
        await handle_set_balance_input(text, chat_id, session, bot)
        return

    # Flow /manajemenakun (submenu: tambah akun)
    if session.get("flow") == "add_account":
        await handle_add_account_input(text, chat_id, session, bot)
        return

    # Flow /tambahcicilan
    if session.get("flow") == "add_installment" and session.get("awaiting"):
        await handle_add_installment_input(text, chat_id, member, session, bot)
        return

    # Flow /updatebunga
    if session.get("flow") == "update_rate" and session.get("awaiting") == "rate_value":
        await handle_update_rate_input(text, chat_id, session, bot)
        return

    # Flow /tambahdeposito
    if session.get("flow") == "add_deposit" and session.get("awaiting"):
        await handle_add_deposit_input(text, chat_id, member, session, bot)
        return

    # Flow /tambahaset
    if session.get("flow") == "add_asset" and session.get("awaiting"):
        await handle_add_asset_input(text, chat_id, member, session, bot)
        return

    # Default: coba parse sebagai transaksi baru
    parsed = parse_transaction_text(text)
    if parsed is None:
        help_text = build_help_text(member, greeting=False)
        await bot.send_message(
            chat_id,
            "Gak ke-detect nominalnya bro 🤔\n"
            "Coba format: `item nominal`\n"
            "Contoh: `kopi 25000` atau `kopi 25rb`\n\n"
            f"{help_text}",
            parse_mode="Markdown",
        )
        return

    draft = {"amount": parsed.amount, "description": parsed.description}
    save_session(chat_id, draft)

    await bot.send_message(
        chat_id,
        f"{format_rupiah(parsed.amount)} - {parsed.description}\nIni transaksi apa?",
        reply_markup=keyboards.build_type_keyboard(),
    )


async def handle_set_balance_input(text: str, chat_id: int, session: dict, bot: Bot) -> None:
    amount = parse_plain_amount(text)  # nerima 0, beda dari parser transaksi biasa
    if amount is None:
        await bot.send_message(
            chat_id,
            "Gak ke-detect nominalnya. Coba ketik angka aja, misal `0` atau `500000`.",
            parse_mode="Markdown",
        )
        return

    account_id = session["pending_account_id"]
    update_account_initial_balance(account_id, amount)
    account = get_account_by_id(account_id)

    session.pop("awaiting", None)
    session.pop("pending_account_id", None)
    save_session(chat_id, session)

    amount_str = format_rupiah(amount)
    await bot.send_message(
        chat_id,
        f"✅ Saldo awal {account.name} diset ke {amount_str}.\nMau atur akun lain?",
        reply_markup=keyboards.build_set_balance_more_keyboard(),
    )


# ============================================
# FLOW: /manajemenakun (submenu: tambah akun)
# ============================================

async def handle_add_account_input(text: str, chat_id: int, session: dict, bot: Bot) -> None:
    if session.get("awaiting") == "account_name":
        session["name"] = text.strip()
        session["awaiting"] = None
        save_session(chat_id, session)
        await bot.send_message(
            chat_id, "Tipe akunnya apa?", reply_markup=keyboards.build_account_type_keyboard()
        )
    elif session.get("awaiting") == "account_balance":
        amount = parse_plain_amount(text)
        if amount is None:
            await bot.send_message(
                chat_id, "Gak ke-detect nominalnya. Ketik angka aja, misal `0` atau `500000`.", parse_mode="Markdown"
            )
            return
        # family_id perlu diambil ulang -> disimpan pas submenu tambah akun dipilih
        family_id = session["family_id"]
        create_account(family_id, session["name"], session["type"], amount)
        clear_session(chat_id)
        amount_str = format_rupiah(amount)
        await bot.send_message(chat_id, f"✅ Akun *{session['name']}* ditambahin, saldo awal {amount_str}.", parse_mode="Markdown")


# ============================================
# FLOW: /tambahcicilan
# ============================================

async def handle_add_installment_input(text: str, chat_id: int, member: FamilyMember, session: dict, bot: Bot) -> None:
    awaiting = session.get("awaiting")

    if awaiting == "installment_name":
        session["name"] = text.strip()
        session["awaiting"] = None
        save_session(chat_id, session)
        accounts = get_accounts(member.family_id)
        await bot.send_message(
            chat_id, "Bayar cicilan ini pakai akun apa?",
            reply_markup=keyboards.build_account_keyboard(accounts, prefix="instacc"),
        )

    elif awaiting == "installment_amount":
        amount = parse_plain_amount(text)
        if amount is None or amount <= 0:
            await bot.send_message(chat_id, "Nominal per bulan gak valid. Ketik angka, misal `500000`.", parse_mode="Markdown")
            return
        session["amount_per_month"] = amount
        session["awaiting"] = "installment_billing_day"
        save_session(chat_id, session)
        await bot.send_message(chat_id, "Tanggal jatuh tempo tiap bulan (1-31)?")

    elif awaiting == "installment_billing_day":
        try:
            day = int(text.strip())
            if not (1 <= day <= 31):
                raise ValueError
        except ValueError:
            await bot.send_message(chat_id, "Ketik angka 1-31 aja ya, misal `15`.", parse_mode="Markdown")
            return
        session["billing_day"] = day
        session["awaiting"] = None
        if session.get("obligation_type") == "subscription":
            # Langganan bulanan gak butuh tenor -> jalan terus sampai di-cancel manual
            session["tenor_months"] = None
            save_session(chat_id, session)
            await _continue_installment_after_tenor(chat_id, session, bot)
        else:
            save_session(chat_id, session)
            await bot.send_message(
                chat_id, "Tenornya gimana?", reply_markup=keyboards.build_tenor_type_keyboard()
            )

    elif awaiting == "installment_tenor_months":
        try:
            tenor = int(text.strip())
            if tenor <= 0:
                raise ValueError
        except ValueError:
            await bot.send_message(chat_id, "Ketik jumlah bulan yang valid, misal `12`.", parse_mode="Markdown")
            return
        session["tenor_months"] = tenor
        session["awaiting"] = None
        save_session(chat_id, session)
        await _continue_installment_after_tenor(chat_id, session, bot)

    elif awaiting == "installment_interest_rate":
        cleaned = text.strip().lower()
        if cleaned in ("skip", "-", ""):
            session["interest_rate_pct"] = None
        else:
            try:
                rate = float(cleaned.replace(",", ".").replace("%", ""))
                session["interest_rate_pct"] = rate
            except ValueError:
                await bot.send_message(chat_id, "Format gak valid. Ketik angka misal `7.5`, atau `skip`.")
                return
        if session["interest_rate_pct"] is not None:
            session["awaiting"] = "installment_fixed_rate_months"
            save_session(chat_id, session)
            await bot.send_message(
                chat_id,
                "Bunga fix ini berlaku berapa bulan sebelum floating? Ketik angka (misal `24`), atau `skip` kalau langsung floating.",
                parse_mode="Markdown",
            )
        else:
            session["fixed_rate_months"] = None
            session["awaiting"] = None
            save_session(chat_id, session)
            await _send_installment_confirmation(chat_id, session, bot)

    elif awaiting == "installment_fixed_rate_months":
        cleaned = text.strip().lower()
        if cleaned in ("skip", "-", ""):
            session["fixed_rate_months"] = None
        else:
            try:
                months = int(cleaned)
                if months <= 0:
                    raise ValueError
                session["fixed_rate_months"] = months
            except ValueError:
                await bot.send_message(chat_id, "Ketik jumlah bulan yang valid, misal `24`, atau `skip`.", parse_mode="Markdown")
                return
        session["awaiting"] = None
        save_session(chat_id, session)
        await _send_installment_confirmation(chat_id, session, bot)


async def _continue_installment_after_tenor(chat_id: int, session: dict, bot: Bot, edit_query=None) -> None:
    if session.get("obligation_type") == "kpr":
        session["awaiting"] = "installment_interest_rate"
        save_session(chat_id, session)
        text = "Suku bunga saat ini (%)? Boleh ketik `skip` kalau belum tau."
        if edit_query:
            await safe_edit_message_text(edit_query, text, parse_mode="Markdown")
        else:
            await bot.send_message(chat_id, text, parse_mode="Markdown")
    else:
        await _send_installment_confirmation(chat_id, session, bot, edit_query=edit_query)


async def _send_installment_confirmation(chat_id: int, session: dict, bot: Bot, edit_query=None) -> None:
    label = {"kpr": "KPR", "subscription": "Langganan Bulanan"}.get(
        session.get("obligation_type"), "Cicilan Kartu Kredit"
    )
    amount_str = format_rupiah(session['amount_per_month'])
    tenor_str = f"{session['tenor_months']} bulan" if session.get("tenor_months") else "Reguler (gak ada batas)"
    lines = [
        f"✅ *Konfirmasi {label}*",
        f"Nama: {session['name']}",
        f"Nominal: {amount_str}/bulan",
        f"Jatuh tempo: tanggal {session['billing_day']}",
        f"Tenor: {tenor_str}",
    ]
    if session.get("interest_rate_pct") is not None:
        rate_line = f"Suku bunga: {session['interest_rate_pct']}% p.a."
        if session.get("fixed_rate_months"):
            rate_line += f" (fix {session['fixed_rate_months']} bulan pertama, lalu floating)"
        lines.append(rate_line)
    text = "\n".join(lines)
    markup = keyboards.build_installment_confirm_keyboard()
    if edit_query:
        await safe_edit_message_text(edit_query, text, reply_markup=markup, parse_mode="Markdown")
    else:
        await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")


# ============================================
# FLOW: /updatebunga
# ============================================

async def handle_update_rate_input(text: str, chat_id: int, session: dict, bot: Bot) -> None:
    try:
        rate = float(text.strip().replace(",", ".").replace("%", ""))
    except ValueError:
        await bot.send_message(chat_id, "Format gak valid. Ketik angka aja, misal `7.5`.", parse_mode="Markdown")
        return
    update_installment_interest_rate(session["target_id"], rate)
    clear_session(chat_id)
    await bot.send_message(chat_id, f"✅ Suku bunga diupdate jadi {rate}% p.a.")


# ============================================
# FLOW: /tambahdeposito
# ============================================

async def handle_add_deposit_input(text: str, chat_id: int, member: FamilyMember, session: dict, bot: Bot) -> None:
    awaiting = session.get("awaiting")

    if awaiting == "deposit_name":
        session["name"] = text.strip()
        session["awaiting"] = "deposit_principal"
        save_session(chat_id, session)
        await bot.send_message(chat_id, "Pokok depositonya berapa?")

    elif awaiting == "deposit_principal":
        amount = parse_plain_amount(text)
        if amount is None or amount <= 0:
            await bot.send_message(chat_id, "Nominal gak valid. Ketik angka, misal `10000000` atau `10jt`.", parse_mode="Markdown")
            return
        session["principal_amount"] = amount
        session["awaiting"] = "deposit_rate"
        save_session(chat_id, session)
        await bot.send_message(chat_id, "Suku bunga p.a. berapa persen? (misal `5.5`)")

    elif awaiting == "deposit_rate":
        try:
            rate = float(text.strip().replace(",", ".").replace("%", ""))
            if rate <= 0:
                raise ValueError
        except ValueError:
            await bot.send_message(chat_id, "Format gak valid. Ketik angka, misal `5.5`.", parse_mode="Markdown")
            return
        session["interest_rate_pct_pa"] = rate
        session["awaiting"] = "deposit_tenor"
        save_session(chat_id, session)
        await bot.send_message(chat_id, "Tenornya berapa bulan?")

    elif awaiting == "deposit_tenor":
        try:
            tenor = int(text.strip())
            if tenor <= 0:
                raise ValueError
        except ValueError:
            await bot.send_message(chat_id, "Ketik jumlah bulan yang valid, misal `12`.", parse_mode="Markdown")
            return
        session["tenor_months"] = tenor
        session["awaiting"] = None
        save_session(chat_id, session)
        await bot.send_message(
            chat_id, "Bunga cair kapan?", reply_markup=keyboards.build_interest_mode_keyboard()
        )

    elif awaiting == "deposit_interest_day":
        try:
            day = int(text.strip())
            if not (1 <= day <= 31):
                raise ValueError
        except ValueError:
            await bot.send_message(chat_id, "Ketik angka 1-31 aja ya, misal `15`.", parse_mode="Markdown")
            return
        session["interest_payment_day"] = day
        session["awaiting"] = None
        save_session(chat_id, session)
        await bot.send_message(
            chat_id, "Bunga bulanan mau kemana?", reply_markup=keyboards.build_interest_payout_mode_keyboard()
        )


async def _send_deposit_confirmation(chat_id: int, session: dict, bot: Bot, edit_query=None) -> None:
    maturity = add_months(date.today(), session["tenor_months"])
    session["maturity_date"] = maturity.isoformat()
    save_session(chat_id, session)

    principal_str = format_rupiah(session['principal_amount'])
    est_interest = session["principal_amount"] * (session["interest_rate_pct_pa"] / 100) * (session["tenor_months"] / 12)
    interest_str = format_rupiah(est_interest)

    lines = [
        "✅ *Konfirmasi Deposito*",
        f"Nama: {session['name']}",
        f"Pokok: {principal_str}",
        f"Bunga: {session['interest_rate_pct_pa']}% p.a.",
        f"Tenor: {session['tenor_months']} bulan",
        f"Jatuh tempo: {maturity.isoformat()}",
    ]

    interest_mode = session.get("interest_mode")
    if interest_mode == "rollover":
        monthly_est = session["principal_amount"] * (session["interest_rate_pct_pa"] / 100) / 12
        lines.append(f"Bunga bulanan (tgl {session['interest_payment_day']}): rollover ke pokok, est. {format_rupiah(monthly_est)}/bln")
    elif interest_mode == "payout":
        monthly_est = session["principal_amount"] * (session["interest_rate_pct_pa"] / 100) / 12
        lines.append(f"Bunga bulanan (tgl {session['interest_payment_day']}): cair ke akun, est. {format_rupiah(monthly_est)}/bln")
    else:
        lines.append(f"Estimasi bunga (di akhir tenor): {interest_str}")

    text = "\n".join(lines)
    markup = keyboards.build_deposit_confirm_keyboard()
    if edit_query:
        await safe_edit_message_text(edit_query, text, reply_markup=markup, parse_mode="Markdown")
    else:
        await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")


ASSET_TYPE_LABELS = {"gold": "Emas", "forex": "Dollar/Valas", "stock": "Saham/Reksadana", "other": "Lainnya"}


# ============================================
# FLOW: /tambahaset
# ============================================

async def handle_add_asset_input(text: str, chat_id: int, member: FamilyMember, session: dict, bot: Bot) -> None:
    awaiting = session.get("awaiting")

    if awaiting == "asset_unit_label":
        unit = text.strip()
        if not unit:
            await bot.send_message(chat_id, "Satuan gak boleh kosong. Ketik misal `USD` atau `barel`.", parse_mode="Markdown")
            return
        session["unit"] = unit
        session["awaiting"] = "asset_name"
        save_session(chat_id, session)
        await bot.send_message(chat_id, "Nama asetnya apa? (misal: Emas Antam)")

    elif awaiting == "asset_name":
        session["name"] = text.strip()
        session["awaiting"] = "asset_quantity"
        save_session(chat_id, session)
        await bot.send_message(chat_id, f"Kuantitasnya berapa {session['unit']}?")

    elif awaiting == "asset_quantity":
        qty = parse_plain_amount(text)
        if qty is None or qty <= 0:
            await bot.send_message(chat_id, "Kuantitas gak valid. Ketik angka, misal `10` atau `10.5`.", parse_mode="Markdown")
            return
        session["quantity"] = qty
        session["awaiting"] = "asset_buy_price"
        save_session(chat_id, session)
        await bot.send_message(chat_id, f"Harga beli per {session['unit']} berapa? (Rupiah)")

    elif awaiting == "asset_buy_price":
        price = parse_plain_amount(text)
        if price is None or price <= 0:
            await bot.send_message(chat_id, "Nominal gak valid. Ketik angka, misal `1350000`.", parse_mode="Markdown")
            return
        session["buy_price"] = price
        session["awaiting"] = None
        save_session(chat_id, session)
        await _send_asset_confirmation(chat_id, session, bot)


async def _send_asset_confirmation(chat_id: int, session: dict, bot: Bot, edit_query=None) -> None:
    qty = session["quantity"]
    unit = session["unit"]
    buy_price = session["buy_price"]
    lines = [
        "✅ *Konfirmasi Aset*",
        f"Tipe: {ASSET_TYPE_LABELS[session['asset_type']]}",
        f"Nama: {session['name']}",
        f"Kuantitas: {qty:g} {unit}",
        f"Harga beli: {format_rupiah(buy_price)}/{unit}",
        f"Total nilai beli: {format_rupiah(qty * buy_price)}",
    ]
    text = "\n".join(lines)
    markup = keyboards.build_asset_confirm_keyboard()
    if edit_query:
        await safe_edit_message_text(edit_query, text, reply_markup=markup, parse_mode="Markdown")
    else:
        await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")


async def handle_register(text: str, chat_id: int, bot: Bot) -> None:
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await bot.send_message(chat_id, "Format: `/daftar KODE`", parse_mode="Markdown")
        return

    code = parts[1].strip().upper()
    member = get_member_by_invite_code(code)

    if member is None:
        await bot.send_message(
            chat_id, "Kode gak valid atau udah pernah dipakai. Minta kode baru ke admin."
        )
        return

    register_member_chat_id(member.id, chat_id)
    await bot.send_message(
        chat_id,
        f"✅ Berhasil terdaftar sebagai *{member.name}*!\nKetik /start buat mulai.",
        parse_mode="Markdown",
    )


async def handle_custom_date_input(text, chat_id, member, session, bot: Bot) -> None:
    parsed_date = _parse_date_string(text)
    if parsed_date is None:
        await bot.send_message(
            chat_id,
            "Format tanggal gak dikenali. Coba `DD/MM` atau `DD/MM/YYYY`, misal `15/07` atau `15/07/2026`.",
            parse_mode="Markdown",
        )
        return

    draft = session
    draft["date"] = parsed_date.isoformat()
    draft.pop("awaiting", None)
    save_session(chat_id, draft)

    await _send_confirmation(chat_id, draft, bot)


def _parse_date_string(text: str) -> date | None:
    text = text.strip()
    for fmt_parts in (3, 2):
        parts = text.replace("-", "/").split("/")
        if len(parts) != fmt_parts:
            continue
        try:
            if fmt_parts == 3:
                day, month, year = parts
                year = int(year)
                if year < 100:
                    year += 2000
            else:
                day, month = parts
                year = date.today().year
            return date(int(year), int(month), int(day))
        except ValueError:
            continue
    return None


# ============================================
# COMMANDS
# ============================================

def build_help_text(member: FamilyMember, greeting: bool = True) -> str:
    lines = []
    if greeting:
        lines.append(f"Halo {member.name}! 👋\n")
        lines.append("Catat transaksi tinggal ketik langsung, contoh:")
        lines.append("`kopi 25000` atau `gaji bulan ini 8jt`\n")
    lines.append("Command yang tersedia:")
    lines.append("\n💰 *Keuangan*")
    lines.append("/saldo - lihat saldo semua akun")
    lines.append("/riwayat [jumlah] - riwayat transaksi (default 10, maks 50)")
    lines.append("\n🏦 *Akun*")
    lines.append("/manajemenakun - tambah/hapus/lihat akun")
    lines.append("/setmodal - atur/koreksi saldo awal akun")
    lines.append("\n🏠 *Cicilan*")
    lines.append("/tambahcicilan - daftar cicilan KK/KPR/langganan baru")
    lines.append("/cicilan - lihat cicilan & langganan aktif")
    lines.append("/updatebunga - update suku bunga KPR")
    lines.append("/kartukredit - ringkasan utang & langganan per kartu")
    lines.append("\n📈 *Deposito*")
    lines.append("/tambahdeposito - daftar deposito baru")
    lines.append("/deposito - lihat deposito aktif")
    lines.append("\n📦 *Aset & Investasi*")
    lines.append("/tambahaset - daftar aset baru (emas/valas/saham/lain)")
    lines.append("/aset - lihat aset & estimasi gain/loss")
    lines.append("/updateharga <nama> <harga> - update harga terkini aset")
    lines.append("\n⚙️ *Lainnya*")
    lines.append("/dashboard - link dashboard rekap keuangan")
    lines.append("/batal - batalin input yang lagi jalan")
    if member.role == "admin":
        lines.append("/undang <nama> - undang anggota keluarga baru")
    return "\n".join(lines)


async def handle_command(text: str, chat_id: int, member: FamilyMember, bot: Bot) -> None:
    # Telegram kadang nyisipin "@namabot" di belakang command (misal pas dipilih dari
    # menu saran) -> "/dashboard@mpenep_bot". Strip dulu biar tetep match ke "/dashboard".
    command = text.split()[0].split("@")[0].lower()

    if command in ("/start", "/help"):
        await bot.send_message(chat_id, build_help_text(member), parse_mode="Markdown")

    elif command == "/saldo":
        accounts = get_accounts(member.family_id)
        if not accounts:
            await bot.send_message(chat_id, "Belum ada akun terdaftar.")
            return
        lines = ["💰 *Saldo saat ini:*\n"]
        total = 0
        for acc in accounts:
            balance = get_account_balance(acc.id)
            total += balance
            lines.append(f"{acc.name}: {format_rupiah(balance)}")
        lines.append(f"\n*Total: {format_rupiah(total)}*")
        await bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")

    elif command == "/riwayat":
        limit = RIWAYAT_DEFAULT_LIMIT
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            try:
                limit = int(parts[1].strip())
            except ValueError:
                limit = RIWAYAT_DEFAULT_LIMIT
        limit = max(1, min(limit, RIWAYAT_MAX_LIMIT))

        txs = get_recent_transactions(member.family_id, limit=limit)
        if not txs:
            await bot.send_message(chat_id, "Belum ada transaksi tercatat.")
            return

        lines = [f"📋 *{len(txs)} transaksi terakhir:*"]
        current_date = None
        for tx in txs:
            date_str = tx["transaction_date"]
            if date_str != current_date:
                current_date = date_str
                lines.append(f"\n📅 *{format_date_id(date_str)}*")

            icon = {"expense": "💸", "income": "💰", "transfer": "🔄"}[tx["type"]]
            acc_name = (tx.get("accounts") or {}).get("name", "?")
            amount_str = format_rupiah(float(tx["amount"]))
            desc = tx.get("description") or ""

            if tx["type"] == "transfer":
                to_acc_name = (tx.get("to_accounts") or {}).get("name", "?")
                label = desc or "Transfer"
                detail = f"{label} ({acc_name} → {to_acc_name})"
            else:
                cat_name = (tx.get("categories") or {}).get("name", "")
                label = " · ".join(p for p in [cat_name, desc] if p)
                detail = f"{label} ({acc_name})" if label else f"({acc_name})"

            lines.append(f"{icon} {amount_str} — {detail}")

        if limit == RIWAYAT_MAX_LIMIT and len(txs) == RIWAYAT_MAX_LIMIT:
            lines.append(f"\n_Dibatasi {RIWAYAT_MAX_LIMIT} transaksi terbaru._")

        await bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")

    elif command == "/undang":
        if member.role != "admin":
            await bot.send_message(chat_id, "Cuma admin yang bisa undang anggota baru.")
            return

        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await bot.send_message(chat_id, "Format: /undang Nama Orangnya")
            return

        import html

        name = parts[1].strip()
        code = create_pending_member(member.family_id, name)
        safe_name = html.escape(name)  # cegah nama yang isinya <, >, & bikin HTML rusak

        if BOT_USERNAME:
            link = f"https://t.me/{BOT_USERNAME}?start={code}"
            await bot.send_message(
                chat_id,
                f"✅ Undangan buat <b>{safe_name}</b> siap!\n\n"
                f"Share link ini ke orangnya:\n{link}\n\n"
                f"Tinggal tap link-nya & tap Start, langsung otomatis terdaftar.\n"
                f"(Kalau link gak bisa dibuka, kode manual: <code>{code}</code>, ketik /daftar {code})",
                parse_mode="HTML",
            )
        else:
            await bot.send_message(
                chat_id,
                f"✅ Kode undangan buat <b>{safe_name}</b>:\n<code>{code}</code>\n\n"
                f"Share kode ini ke orangnya, suruh chat bot ini dan ketik: /daftar {code}",
                parse_mode="HTML",
            )

    elif command == "/setmodal":
        accounts = get_accounts(member.family_id)
        if not accounts:
            await bot.send_message(chat_id, "Belum ada akun terdaftar.")
            return
        session = {"flow": "set_balance"}
        save_session(chat_id, session)
        await bot.send_message(
            chat_id,
            "Mau atur saldo awal akun mana?",
            reply_markup=keyboards.build_account_keyboard(accounts, prefix="setacc"),
        )

    elif command == "/manajemenakun":
        session = {"flow": "manage_account"}
        save_session(chat_id, session)
        await bot.send_message(chat_id, "Mau ngapain?", reply_markup=keyboards.build_account_menu_keyboard())

    elif command == "/tambahcicilan":
        session = {"flow": "add_installment"}
        save_session(chat_id, session)
        await bot.send_message(
            chat_id, "Ini cicilan apa?", reply_markup=keyboards.build_obligation_type_keyboard()
        )

    elif command == "/cicilan":
        installments = get_active_installments(member.family_id)
        if not installments:
            await bot.send_message(chat_id, "Belum ada cicilan/KPR terdaftar. Coba /tambahcicilan.")
            return
        lines = ["📋 *Cicilan, KPR & Langganan aktif:*\n"]
        total = 0.0
        for inst in installments:
            label = {"kpr": "KPR", "subscription": "Langganan"}.get(inst.obligation_type, "Cicilan KK")
            amount_str = format_rupiah(inst.amount_per_month)
            tenor_str = (
                f"{inst.months_paid}/{inst.tenor_months} bulan"
                if inst.tenor_months
                else f"bulan ke-{inst.months_paid + 1} (reguler)"
            )
            rate_str = f" · {inst.interest_rate_pct}% p.a." if inst.interest_rate_pct else ""
            if inst.interest_rate_pct and inst.fixed_rate_months:
                rate_str += f" (fix {inst.fixed_rate_months} bln)"
            lines.append(
                f"[{label}] {inst.name}: {amount_str}/bln (tgl {inst.billing_day}) — {tenor_str}{rate_str}"
            )
            total += inst.amount_per_month
        lines.append(f"\n*Estimasi total bulan ini: {format_rupiah(total)}*")
        await bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")

    elif command == "/updatebunga":
        kpr_list = [i for i in get_active_installments(member.family_id) if i.obligation_type == "kpr"]
        if not kpr_list:
            await bot.send_message(chat_id, "Belum ada KPR terdaftar. Coba /tambahcicilan dulu.")
            return
        if len(kpr_list) == 1:
            session = {"flow": "update_rate", "target_id": kpr_list[0].id, "awaiting": "rate_value"}
            save_session(chat_id, session)
            await bot.send_message(chat_id, f"Suku bunga baru buat *{kpr_list[0].name}* (%)?", parse_mode="Markdown")
        else:
            session = {"flow": "update_rate"}
            save_session(chat_id, session)
            await bot.send_message(
                chat_id, "KPR yang mana?", reply_markup=keyboards.build_pick_kpr_keyboard(kpr_list)
            )

    elif command == "/kartukredit":
        cards = [a for a in get_accounts(member.family_id) if a.type == "credit_card"]
        if not cards:
            await bot.send_message(chat_id, "Belum ada akun tipe kartu kredit. Tambah dulu lewat /manajemenakun.")
            return

        installments = get_active_installments(member.family_id)
        lines = ["💳 *Ringkasan Kartu Kredit:*"]
        for card in cards:
            outstanding = -get_account_balance(card.id)  # expense bikin balance negatif = utang
            spend_this_month = get_account_expense_this_month(card.id)
            card_items = [i for i in installments if i.credit_card_id == card.id]

            lines.append(f"\n*{card.name}*")
            lines.append(f"Utang saat ini: {format_rupiah(max(outstanding, 0))}")
            lines.append(f"Total transaksi bulan ini: {format_rupiah(spend_this_month)}")

            if card_items:
                for inst in card_items:
                    label = {"kpr": "KPR", "subscription": "Langganan"}.get(inst.obligation_type, "Cicilan")
                    lines.append(f"  · [{label}] {inst.name}: {format_rupiah(inst.amount_per_month)}/bln")
            else:
                lines.append("  Belum ada cicilan/langganan yang nempel di kartu ini.")

        await bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")

    elif command == "/tambahdeposito":
        session = {"flow": "add_deposit", "awaiting": "deposit_name"}
        save_session(chat_id, session)
        await bot.send_message(chat_id, "Nama depositonya apa? (misal: Deposito BCA)")

    elif command == "/deposito":
        deposits = get_active_deposits(member.family_id)
        if not deposits:
            await bot.send_message(chat_id, "Belum ada deposito terdaftar. Coba /tambahdeposito.")
            return
        lines = ["📋 *Deposito aktif:*\n"]
        today = date.today()
        for dep in deposits:
            maturity = date.fromisoformat(dep.maturity_date)
            days_left = (maturity - today).days
            principal_str = format_rupiah(dep.principal_amount)
            lines.append(
                f"{dep.name}: {principal_str} @ {dep.interest_rate_pct_pa}% p.a.\n"
                f"  Jatuh tempo: {dep.maturity_date} ({days_left} hari lagi)"
            )
            if dep.interest_mode == "rollover":
                lines.append(f"  Bunga bulanan (tgl {dep.interest_payment_day}): rollover ke pokok")
            elif dep.interest_mode == "payout":
                lines.append(f"  Bunga bulanan (tgl {dep.interest_payment_day}): cair ke akun")
            else:
                est_interest = dep.principal_amount * (dep.interest_rate_pct_pa / 100) * (dep.tenor_months / 12)
                interest_str = format_rupiah(est_interest)
                lines.append(f"  Est. bunga (di akhir tenor): {interest_str}")
        await bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")

    elif command == "/tambahaset":
        session = {"flow": "add_asset"}
        save_session(chat_id, session)
        await bot.send_message(
            chat_id, "Aset apa yang mau ditambahin?", reply_markup=keyboards.build_asset_type_keyboard()
        )

    elif command == "/aset":
        assets = get_assets(member.family_id)
        if not assets:
            await bot.send_message(chat_id, "Belum ada aset terdaftar. Coba /tambahaset.")
            return

        lines = ["📦 *Aset & Investasi:*"]
        total_current = 0.0
        total_buy = 0.0
        current_type = None
        for a in assets:
            if a.asset_type != current_type:
                current_type = a.asset_type
                lines.append(f"\n*{ASSET_TYPE_LABELS[a.asset_type]}*")
            current_value = a.quantity * a.current_price
            buy_value = a.quantity * a.buy_price
            gain = current_value - buy_value
            gain_pct = (gain / buy_value * 100) if buy_value else 0
            total_current += current_value
            total_buy += buy_value
            sign = "+" if gain >= 0 else ""
            lines.append(
                f"{a.name}: {a.quantity:g} {a.unit} @ {format_rupiah(a.current_price)}\n"
                f"  Nilai sekarang: {format_rupiah(current_value)} ({sign}{format_rupiah(gain)}, {sign}{gain_pct:.1f}%)"
            )
            if a.last_price_update:
                lines.append(f"  Update harga terakhir: {a.last_price_update}")

        total_gain = total_current - total_buy
        sign = "+" if total_gain >= 0 else ""
        lines.append(f"\n*Total nilai aset: {format_rupiah(total_current)}* ({sign}{format_rupiah(total_gain)})")
        await bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")

    elif command == "/updateharga":
        parts = text.split()
        if len(parts) < 3:
            await bot.send_message(
                chat_id,
                "Format: `/updateharga <nama aset> <harga baru>`\nContoh: `/updateharga Emas Antam 1350000`",
                parse_mode="Markdown",
            )
            return
        price = parse_plain_amount(parts[-1])
        if price is None or price <= 0:
            await bot.send_message(chat_id, "Harga gak valid. Ketik angka, misal `1350000`.", parse_mode="Markdown")
            return
        asset_name = " ".join(parts[1:-1])
        asset = get_asset_by_name(member.family_id, asset_name)
        if asset is None:
            assets = get_assets(member.family_id)
            if assets:
                names = ", ".join(a.name for a in assets)
                await bot.send_message(chat_id, f"Aset '{asset_name}' gak ketemu. Aset yang ada: {names}")
            else:
                await bot.send_message(chat_id, f"Aset '{asset_name}' gak ketemu. Belum ada aset terdaftar, coba /tambahaset.")
            return
        update_asset_price(asset.id, price, date.today())
        await bot.send_message(chat_id, f"✅ Harga {asset.name} diupdate ke {format_rupiah(price)}/{asset.unit}.")

    elif command == "/dashboard":
        if not DASHBOARD_URL:
            await bot.send_message(chat_id, "Link dashboard belum diset. Hubungi admin buat setting env `DASHBOARD_URL`.")
            return
        await bot.send_message(chat_id, f"📊 Dashboard rekap keuangan:\n{DASHBOARD_URL}")

    elif command == "/batal":
        clear_session(chat_id)
        await bot.send_message(chat_id, "Oke, dibatalin.")

    else:
        await bot.send_message(chat_id, "Command gak dikenal. Coba /start buat lihat menu.")


# ============================================
# CALLBACK QUERY (tombol)
# ============================================

async def handle_callback(callback_query, bot: Bot) -> None:
    chat_id = callback_query.message.chat_id
    data = callback_query.data

    # PENTING: answer() harus dipanggil PALING AWAL, sebelum query DB apapun.
    # Telegram anggap callback query "expired" kalau kelamaan gak dijawab,
    # jadi gak boleh ada operasi lambat (network call ke Supabase, dst)
    # sebelum baris ini.
    try:
        await callback_query.answer()
    except BadRequest:
        pass  # query udah expired/kejawab duluan -> gapapa, tetep lanjut proses

    member = get_member_by_chat_id(chat_id)

    if member is None:
        await bot.send_message(chat_id, "Kamu belum terdaftar buat pakai bot ini.")
        return

    if data == "cancel" or data == "confirm:cancel":
        clear_session(chat_id)
        await safe_edit_message_text(callback_query, "❌ Dibatalkan.")
        return

    session = get_session(chat_id)
    prefix, _, value = data.partition(":")

    if prefix == "type":
        session["type"] = value
        save_session(chat_id, session)

        if value == "transfer":
            accounts = get_accounts(member.family_id)
            await safe_edit_message_text(callback_query, 
                "Transfer dari akun mana?",
                reply_markup=keyboards.build_account_keyboard(accounts, prefix="acc"),
            )
        else:
            categories = get_categories(member.family_id, type=value)
            await safe_edit_message_text(callback_query, 
                "Pilih kategori:",
                reply_markup=keyboards.build_category_keyboard(categories),
            )

    elif prefix == "cat":
        session["category_id"] = value
        save_session(chat_id, session)
        accounts = get_accounts(member.family_id)
        await safe_edit_message_text(callback_query, 
            "Pakai akun apa?",
            reply_markup=keyboards.build_account_keyboard(accounts, prefix="acc"),
        )

    elif prefix == "acc":
        session["account_id"] = value
        save_session(chat_id, session)

        if session.get("type") == "transfer":
            all_accounts = get_accounts(member.family_id)
            other_accounts = [a for a in all_accounts if a.id != value]
            await safe_edit_message_text(callback_query, 
                "Transfer ke akun mana?",
                reply_markup=keyboards.build_account_keyboard(other_accounts, prefix="toacc"),
            )
        else:
            await safe_edit_message_text(callback_query, 
                "Tanggal transaksi?",
                reply_markup=keyboards.build_date_keyboard(),
            )

    elif prefix == "toacc":
        session["to_account_id"] = value
        save_session(chat_id, session)
        await safe_edit_message_text(callback_query, 
            "Tanggal transaksi?",
            reply_markup=keyboards.build_date_keyboard(),
        )

    elif prefix == "date":
        if value == "today":
            session["date"] = date.today().isoformat()
        elif value == "yesterday":
            session["date"] = (date.today() - timedelta(days=1)).isoformat()
        elif value == "custom":
            session["awaiting"] = "custom_date"
            save_session(chat_id, session)
            await safe_edit_message_text(callback_query, 
                "Ketik tanggalnya, format `DD/MM` atau `DD/MM/YYYY`:",
                parse_mode="Markdown",
            )
            return

        save_session(chat_id, session)
        await _send_confirmation(chat_id, session, bot, edit_query=callback_query)

    elif prefix == "setacc":
        session["pending_account_id"] = value
        session["awaiting"] = "balance_amount"
        save_session(chat_id, session)
        account = get_account_by_id(value)
        await safe_edit_message_text(
            callback_query,
            f"Ketik saldo saat ini untuk *{account.name}*, misal `500000` atau `500rb`:",
            parse_mode="Markdown",
        )

    elif prefix == "setmore":
        if value == "yes":
            accounts = get_accounts(member.family_id)
            session = {"flow": "set_balance"}
            save_session(chat_id, session)
            await safe_edit_message_text(
                callback_query,
                "Mau atur saldo awal akun mana?",
                reply_markup=keyboards.build_account_keyboard(accounts, prefix="setacc"),
            )
        else:
            clear_session(chat_id)
            await safe_edit_message_text(
                callback_query, "✅ Oke, semua diatur. Ketik /saldo buat cek."
            )

    elif prefix == "acctmenu":
        if value == "add":
            session["flow"] = "add_account"
            session["awaiting"] = "account_name"
            session["family_id"] = member.family_id
            save_session(chat_id, session)
            await safe_edit_message_text(callback_query, "Nama akunnya apa?")
        elif value == "delete":
            accounts = get_accounts(member.family_id)
            if not accounts:
                await safe_edit_message_text(callback_query, "Belum ada akun terdaftar.")
                return
            await safe_edit_message_text(
                callback_query,
                "Akun mana yang mau dihapus?",
                reply_markup=keyboards.build_account_keyboard(accounts, prefix="delacc"),
            )
        else:  # list
            accounts = get_accounts(member.family_id)
            if not accounts:
                await safe_edit_message_text(callback_query, "Belum ada akun terdaftar.")
                return
            lines = ["📋 *Daftar akun:*\n"]
            for acc in accounts:
                balance = get_account_balance(acc.id)
                lines.append(f"{acc.name} ({acc.type}): {format_rupiah(balance)}")
            await safe_edit_message_text(callback_query, "\n".join(lines), parse_mode="Markdown")

    elif prefix == "delacc":
        account = get_account_by_id(value)
        if account_has_dependencies(value):
            await safe_edit_message_text(
                callback_query,
                f"❌ *{account.name}* gak bisa dihapus karena udah punya riwayat transaksi/cicilan.\n"
                "Akun dengan riwayat data gak boleh dihapus biar data lama gak rusak.",
                parse_mode="Markdown",
            )
            return
        await safe_edit_message_text(
            callback_query,
            f"Yakin mau hapus *{account.name}*? Ini gak bisa dibatalin.",
            reply_markup=keyboards.build_delete_account_confirm_keyboard(value),
            parse_mode="Markdown",
        )

    elif prefix == "delconfirm":
        action, _, account_id = value.partition(":")
        if action == "yes":
            account = get_account_by_id(account_id)
            delete_account(account_id)
            clear_session(chat_id)
            await safe_edit_message_text(callback_query, f"🗑️ {account.name} udah dihapus.")
        else:
            clear_session(chat_id)
            await safe_edit_message_text(callback_query, "❌ Dibatalkan.")

    elif prefix == "acctype":
        session["type"] = value
        session["awaiting"] = "account_balance"
        save_session(chat_id, session)
        await safe_edit_message_text(
            callback_query, "Saldo awal berapa? (boleh `0` kalau belum mau diisi)", parse_mode="Markdown"
        )

    elif prefix == "obligtype":
        session["obligation_type"] = value
        session["awaiting"] = "installment_name"
        save_session(chat_id, session)
        label = {"kpr": "KPR", "subscription": "langganan"}.get(value, "cicilan kartu kredit")
        await safe_edit_message_text(callback_query, f"Nama {label} ini apa?")

    elif prefix == "tenortype":
        if value == "fixed":
            session["awaiting"] = "installment_tenor_months"
            save_session(chat_id, session)
            await safe_edit_message_text(callback_query, "Tenornya berapa bulan?")
        else:
            session["tenor_months"] = None
            save_session(chat_id, session)
            await _continue_installment_after_tenor(chat_id, session, bot, edit_query=callback_query)

    elif prefix == "instacc":
        session["funding_account_id"] = value
        save_session(chat_id, session)
        if session.get("obligation_type") in ("cicilan_kk", "subscription"):
            cc_accounts = [a for a in get_accounts(member.family_id) if a.type == "credit_card"]
            if not cc_accounts:
                session["credit_card_id"] = None
                save_session(chat_id, session)
                categories = get_categories(member.family_id, type="expense")
                await safe_edit_message_text(
                    callback_query,
                    "Belum ada akun tipe kartu kredit terdaftar, lanjut pilih kategori aja.\n\nPilih kategori:",
                    reply_markup=keyboards.build_category_keyboard(categories, prefix="instcat"),
                )
            else:
                await safe_edit_message_text(
                    callback_query,
                    "Kartu kredit yang mana?",
                    reply_markup=keyboards.build_account_keyboard(cc_accounts, prefix="instcard"),
                )
        else:
            categories = get_categories(member.family_id, type="expense")
            await safe_edit_message_text(
                callback_query, "Pilih kategori:", reply_markup=keyboards.build_category_keyboard(categories, prefix="instcat")
            )

    elif prefix == "instcard":
        session["credit_card_id"] = value
        save_session(chat_id, session)
        categories = get_categories(member.family_id, type="expense")
        await safe_edit_message_text(
            callback_query, "Pilih kategori:", reply_markup=keyboards.build_category_keyboard(categories, prefix="instcat")
        )

    elif prefix == "instcat":
        session["category_id"] = value
        session["awaiting"] = "installment_amount"
        save_session(chat_id, session)
        await safe_edit_message_text(callback_query, "Nominal per bulan berapa?")

    elif prefix == "intmode":
        if value == "tenor":
            session["interest_mode"] = None
            session["interest_payment_day"] = None
            save_session(chat_id, session)
            accounts = get_accounts(member.family_id)
            await safe_edit_message_text(
                callback_query,
                "Ada akun terkait (opsional, buat referensi doang)?",
                reply_markup=keyboards.build_deposit_skip_account_keyboard(accounts, allow_skip=True),
            )
        else:  # monthly
            session["awaiting"] = "deposit_interest_day"
            save_session(chat_id, session)
            await safe_edit_message_text(callback_query, "Tanggal cair tiap bulan (1-31)?")

    elif prefix == "payoutmode":
        session["interest_mode"] = value  # 'rollover' atau 'payout'
        save_session(chat_id, session)
        accounts = get_accounts(member.family_id)
        if value == "payout":
            await safe_edit_message_text(
                callback_query,
                "Bunga bulanan cair ke akun mana?",
                reply_markup=keyboards.build_deposit_skip_account_keyboard(accounts, allow_skip=False),
            )
        else:
            await safe_edit_message_text(
                callback_query,
                "Ada akun terkait (opsional, buat referensi doang)?",
                reply_markup=keyboards.build_deposit_skip_account_keyboard(accounts, allow_skip=True),
            )

    elif prefix == "depoacc":
        if session.get("interest_mode") == "payout":
            session["receival_account_id"] = value  # gak pernah 'skip' -> gak ditawarin di mode ini
        else:
            session["account_id"] = None if value == "skip" else value
        save_session(chat_id, session)
        await _send_deposit_confirmation(chat_id, session, bot, edit_query=callback_query)

    elif prefix == "pickkpr":
        session["target_id"] = value
        session["awaiting"] = "rate_value"
        save_session(chat_id, session)
        await safe_edit_message_text(callback_query, "Suku bunga baru (%)?")

    elif prefix == "assettype":
        session["asset_type"] = value
        if value in ("forex", "other"):
            session["awaiting"] = "asset_unit_label"
            save_session(chat_id, session)
            prompt = "Mata uangnya apa? (misal USD, SGD)" if value == "forex" else "Satuan aset ini apa? (misal: barel, oz, unit)"
            await safe_edit_message_text(callback_query, prompt)
        else:
            session["unit"] = {"gold": "gram", "stock": "lot"}[value]
            session["awaiting"] = "asset_name"
            save_session(chat_id, session)
            await safe_edit_message_text(callback_query, "Nama asetnya apa? (misal: Emas Antam)")

    elif data == "instconfirm:save":
        create_installment(
            family_id=member.family_id,
            obligation_type=session["obligation_type"],
            name=session["name"],
            funding_account_id=session["funding_account_id"],
            amount_per_month=session["amount_per_month"],
            billing_day=session["billing_day"],
            category_id=session.get("category_id"),
            credit_card_id=session.get("credit_card_id"),
            tenor_months=session.get("tenor_months"),
            interest_rate_pct=session.get("interest_rate_pct"),
            fixed_rate_months=session.get("fixed_rate_months"),
        )
        clear_session(chat_id)
        await safe_edit_message_text(callback_query, f"✅ {session['name']} berhasil didaftarkan!")

    elif data == "instconfirm:cancel":
        clear_session(chat_id)
        await safe_edit_message_text(callback_query, "❌ Dibatalkan.")

    elif data == "depoconfirm:save":
        maturity = date.fromisoformat(session["maturity_date"])
        create_deposit(
            family_id=member.family_id,
            name=session["name"],
            principal_amount=session["principal_amount"],
            interest_rate_pct_pa=session["interest_rate_pct_pa"],
            tenor_months=session["tenor_months"],
            maturity_date=maturity,
            account_id=session.get("account_id"),
            interest_payment_day=session.get("interest_payment_day"),
            interest_mode=session.get("interest_mode"),
            receival_account_id=session.get("receival_account_id"),
        )
        clear_session(chat_id)
        await safe_edit_message_text(callback_query, f"✅ Deposito {session['name']} berhasil didaftarkan!")

    elif data == "depoconfirm:cancel":
        clear_session(chat_id)
        await safe_edit_message_text(callback_query, "❌ Dibatalkan.")

    elif data == "assetconfirm:save":
        create_asset(
            family_id=member.family_id,
            name=session["name"],
            asset_type=session["asset_type"],
            unit=session["unit"],
            quantity=session["quantity"],
            buy_price=session["buy_price"],
        )
        clear_session(chat_id)
        await safe_edit_message_text(callback_query, f"✅ {session['name']} berhasil didaftarkan!")

    elif data == "assetconfirm:cancel":
        clear_session(chat_id)
        await safe_edit_message_text(callback_query, "❌ Dibatalkan.")

    elif prefix == "instpay":
        # format: instpay:confirm:<id> atau instpay:skip:<id>
        action, _, installment_id = value.partition(":")
        installment = get_installment_by_id(installment_id)
        if installment is None:
            await safe_edit_message_text(callback_query, "Cicilan ini udah gak ada/berubah.")
            return
        current_month = date.today().strftime("%Y-%m")

        if action == "confirm":
            insert_transaction(
                family_id=installment.family_id,
                member_id=member.id,
                type="expense",
                account_id=installment.funding_account_id,
                amount=installment.amount_per_month,
                description=installment.name,
                transaction_date=date.today(),
                category_id=installment.category_id,
                source="telegram",
            )
            new_paid = increment_installment_months_paid(installment.id)
            completed = installment.tenor_months is not None and new_paid >= installment.tenor_months
            mark_installment_charged(installment.id, current_month, completed=completed)
            msg = f"✅ {installment.name} dicatat sebagai lunas bulan ini."
            if completed:
                msg += f"\n🎉 Cicilan ini udah LUNAS semua ({installment.tenor_months} bulan)!"
            await safe_edit_message_text(callback_query, msg)
        else:  # skip
            mark_installment_charged(installment.id, current_month, completed=False)
            await safe_edit_message_text(callback_query, f"⏭️ {installment.name} dilewati bulan ini.")

    elif prefix == "depodismiss":
        deposit_id = value
        dismiss_deposit_reminder(deposit_id)
        await safe_edit_message_text(callback_query, "✅ Oke, gak bakal diingetin lagi sampai jatuh tempo.")

    elif prefix == "depomatur":
        # format: depomatur:extend:<id> atau depomatur:withdraw:<id>
        action, _, deposit_id = value.partition(":")
        deposit = get_deposit_by_id(deposit_id)
        if deposit is None:
            await safe_edit_message_text(callback_query, "Deposito ini udah gak ada/berubah.")
            return
        if action == "extend":
            interest_earned = deposit.principal_amount * (deposit.interest_rate_pct_pa / 100) * (deposit.tenor_months / 12)
            new_principal = deposit.principal_amount + interest_earned
            new_maturity = add_months(date.fromisoformat(deposit.maturity_date), deposit.tenor_months)
            rollover_deposit(deposit.id, new_principal, new_maturity)
            principal_str = format_rupiah(new_principal)
            interest_str = format_rupiah(interest_earned)
            await safe_edit_message_text(
                callback_query,
                f"🔄 {deposit.name} diperpanjang!\nBunga {interest_str} digabung ke pokok.\n"
                f"Pokok baru: {principal_str}\nJatuh tempo berikutnya: {new_maturity.isoformat()}",
            )
        else:
            update_deposit_status(deposit_id, "withdrawn")
            await safe_edit_message_text(callback_query, f"💰 {deposit.name} ditandai udah dicairkan.")

    elif prefix == "intpay":
        # format: intpay:confirm:<id> atau intpay:skip:<id>
        action, _, deposit_id = value.partition(":")
        deposit = get_deposit_by_id(deposit_id)
        if deposit is None:
            await safe_edit_message_text(callback_query, "Deposito ini udah gak ada/berubah.")
            return
        current_month = date.today().strftime("%Y-%m")
        monthly_interest = deposit.principal_amount * (deposit.interest_rate_pct_pa / 100) / 12

        if action == "confirm":
            insert_transaction(
                family_id=deposit.family_id,
                member_id=member.id,
                type="income",
                account_id=deposit.receival_account_id,
                amount=monthly_interest,
                description=f"Bunga {deposit.name}",
                transaction_date=date.today(),
                source="telegram",
            )
            update_deposit_last_interest_month(deposit.id, current_month)
            interest_str = format_rupiah(monthly_interest)
            await safe_edit_message_text(callback_query, f"✅ Bunga {deposit.name} {interest_str} dicatat masuk.")
        else:
            update_deposit_last_interest_month(deposit.id, current_month)
            await safe_edit_message_text(callback_query, f"⏭️ Bunga {deposit.name} bulan ini dilewati.")

    elif data == "confirm:save":
        await _finalize_transaction(chat_id, member, session, bot, callback_query)


# ============================================
# HELPERS
# ============================================

async def _send_confirmation(chat_id, draft, bot: Bot, edit_query=None) -> None:
    type_label = TYPE_LABELS.get(draft.get("type"), draft.get("type"))
    amount_str = format_rupiah(draft['amount'])
    lines = [f"✅ *Konfirmasi {type_label}*", f"{amount_str} - {draft.get('description', '')}"]

    account = get_account_by_id(draft["account_id"]) if draft.get("account_id") else None
    if account:
        lines.append(f"Akun: {account.name}")

        # Preview saldo: sekarang vs proyeksi setelah transaksi ini disimpan
        current_balance = get_account_balance(account.id)
        if draft.get("type") == "income":
            projected = current_balance + draft["amount"]
        else:  # expense atau transfer (keduanya ngurangin saldo akun sumber)
            projected = current_balance - draft["amount"]
        lines.append(
            f"Saldo {account.name}: {format_rupiah(current_balance)} → {format_rupiah(projected)}"
        )

    if draft.get("type") == "transfer":
        to_account = get_account_by_id(draft["to_account_id"])
        if to_account:
            to_current = get_account_balance(to_account.id)
            to_projected = to_current + draft["amount"]
            lines.append(f"Ke: {to_account.name}")
            lines.append(
                f"Saldo {to_account.name}: {format_rupiah(to_current)} → {format_rupiah(to_projected)}"
            )
    else:
        category = get_category_by_id(draft["category_id"]) if draft.get("category_id") else None
        if category:
            lines.append(f"Kategori: {category.name}")

    lines.append(f"Tanggal: {draft.get('date')}")

    text = "\n".join(lines)
    markup = keyboards.build_confirm_keyboard()

    if edit_query:
        await safe_edit_message_text(edit_query, text, reply_markup=markup, parse_mode="Markdown")
    else:
        await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")


async def _finalize_transaction(chat_id, member: FamilyMember, draft: dict, bot: Bot, callback_query) -> None:
    tx_date = date.fromisoformat(draft["date"])

    insert_transaction(
        family_id=member.family_id,
        member_id=member.id,
        type=draft["type"],
        account_id=draft["account_id"],
        amount=draft["amount"],
        description=draft.get("description", ""),
        transaction_date=tx_date,
        category_id=draft.get("category_id"),
        to_account_id=draft.get("to_account_id"),
        source="telegram",
    )
    clear_session(chat_id)

    new_balance = get_account_balance(draft["account_id"])
    account = get_account_by_id(draft["account_id"])
    balance_str = format_rupiah(new_balance)

    await safe_edit_message_text(callback_query, 
        f"✅ Tersimpan!\nSaldo {account.name}: {balance_str}"
    )