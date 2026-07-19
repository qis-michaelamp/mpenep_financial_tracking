"""
Builder untuk semua inline keyboard yang dipakai bot.
Callback data pakai format "prefix:value" biar gampang di-parse di handler.
UUID Supabase (36 char) + prefix pendek masih jauh di bawah limit 64 byte Telegram.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.supabase_client import Account, Category


def build_type_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("💸 Expense", callback_data="type:expense"),
            InlineKeyboardButton("💰 Income", callback_data="type:income"),
        ],
        [InlineKeyboardButton("🔄 Transfer", callback_data="type:transfer")],
        [InlineKeyboardButton("❌ Batal", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(buttons)


def build_category_keyboard(categories: list[Category], prefix: str = "cat") -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for cat in categories:
        label = f"{cat.icon or ''} {cat.name}".strip()
        row.append(InlineKeyboardButton(label, callback_data=f"{prefix}:{cat.id}"))
        if len(row) == 2:  # 2 tombol per baris biar gak kepanjangan di HP
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ Batal", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)


def build_account_keyboard(
    accounts: list[Account], prefix: str = "acc"
) -> InlineKeyboardMarkup:
    """prefix beda buat bedain akun sumber ('acc') vs akun tujuan transfer ('toacc')"""
    icons = {"bank": "🏦", "ewallet": "📱", "cash": "💵"}
    buttons = []
    row = []
    for acc in accounts:
        label = f"{icons.get(acc.type, '💳')} {acc.name}"
        row.append(InlineKeyboardButton(label, callback_data=f"{prefix}:{acc.id}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ Batal", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)


def build_date_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("📅 Hari ini", callback_data="date:today"),
            InlineKeyboardButton("📅 Kemarin", callback_data="date:yesterday"),
        ],
        [InlineKeyboardButton("📅 Tanggal lain", callback_data="date:custom")],
        [InlineKeyboardButton("❌ Batal", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(buttons)


def build_confirm_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("✅ Simpan", callback_data="confirm:save"),
            InlineKeyboardButton("❌ Batal", callback_data="confirm:cancel"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def build_set_balance_more_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("➡️ Atur akun lain", callback_data="setmore:yes"),
            InlineKeyboardButton("✅ Selesai", callback_data="setmore:no"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def build_account_type_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("🏦 Bank", callback_data="acctype:bank"),
            InlineKeyboardButton("📱 E-wallet", callback_data="acctype:ewallet"),
        ],
        [
            InlineKeyboardButton("💵 Cash", callback_data="acctype:cash"),
            InlineKeyboardButton("💳 Kartu Kredit", callback_data="acctype:credit_card"),
        ],
        [InlineKeyboardButton("❌ Batal", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(buttons)


def build_account_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("➕ Tambah Akun", callback_data="acctmenu:add")],
        [InlineKeyboardButton("🗑️ Hapus Akun", callback_data="acctmenu:delete")],
        [InlineKeyboardButton("📋 Lihat Akun", callback_data="acctmenu:list")],
        [InlineKeyboardButton("❌ Batal", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(buttons)


def build_delete_account_confirm_keyboard(account_id: str) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("✅ Ya, hapus", callback_data=f"delconfirm:yes:{account_id}"),
            InlineKeyboardButton("❌ Batal", callback_data="delconfirm:no"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def build_obligation_type_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("💳 Cicilan Kartu Kredit", callback_data="obligtype:cicilan_kk")],
        [InlineKeyboardButton("🏠 KPR", callback_data="obligtype:kpr")],
        [InlineKeyboardButton("🔁 Langganan Bulanan", callback_data="obligtype:subscription")],
        [InlineKeyboardButton("❌ Batal", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(buttons)


def build_tenor_type_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("📅 Ada tenor tetap", callback_data="tenortype:fixed")],
        [InlineKeyboardButton("🔄 Reguler terus-menerus", callback_data="tenortype:indefinite")],
        [InlineKeyboardButton("❌ Batal", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(buttons)


def build_installment_confirm_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("✅ Simpan", callback_data="instconfirm:save"),
            InlineKeyboardButton("❌ Batal", callback_data="instconfirm:cancel"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def build_deposit_confirm_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("✅ Simpan", callback_data="depoconfirm:save"),
            InlineKeyboardButton("❌ Batal", callback_data="depoconfirm:cancel"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def build_deposit_skip_account_keyboard(accounts: list[Account], prefix: str = "depoacc", allow_skip: bool = True) -> InlineKeyboardMarkup:
    """Buat pilih akun terkait deposito. allow_skip=False dipakai buat akun penerima bunga (wajib diisi)."""
    icons = {"bank": "🏦", "ewallet": "📱", "cash": "💵", "credit_card": "💳"}
    buttons = []
    row = []
    for acc in accounts:
        label = f"{icons.get(acc.type, '💳')} {acc.name}"
        row.append(InlineKeyboardButton(label, callback_data=f"{prefix}:{acc.id}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    if allow_skip:
        buttons.append([InlineKeyboardButton("⏭️ Skip (gak perlu)", callback_data=f"{prefix}:skip")])
    buttons.append([InlineKeyboardButton("❌ Batal", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)


def build_interest_mode_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("⏳ Nunggu tenor abis", callback_data="intmode:tenor")],
        [InlineKeyboardButton("📅 Bulanan", callback_data="intmode:monthly")],
        [InlineKeyboardButton("❌ Batal", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(buttons)


def build_interest_payout_mode_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🔄 Rollover ke pokok", callback_data="payoutmode:rollover")],
        [InlineKeyboardButton("💰 Cairkan ke akun", callback_data="payoutmode:payout")],
        [InlineKeyboardButton("❌ Batal", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(buttons)


def build_interest_payout_confirm_keyboard(deposit_id: str) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("✅ Konfirmasi", callback_data=f"intpay:confirm:{deposit_id}"),
            InlineKeyboardButton("⏭️ Lewati", callback_data=f"intpay:skip:{deposit_id}"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def build_installment_reminder_keyboard(installment_id: str) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("✅ Sudah Bayar", callback_data=f"instpay:confirm:{installment_id}"),
            InlineKeyboardButton("⏭️ Lewati Bulan Ini", callback_data=f"instpay:skip:{installment_id}"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def build_deposit_dismiss_keyboard(deposit_id: str) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton("✅ Sudah Disiapkan", callback_data=f"depodismiss:{deposit_id}")]]
    return InlineKeyboardMarkup(buttons)


def build_pick_kpr_keyboard(installments) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(inst.name, callback_data=f"pickkpr:{inst.id}")] for inst in installments]
    buttons.append([InlineKeyboardButton("❌ Batal", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)


def build_deposit_maturity_keyboard(deposit_id: str) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("🔄 Perpanjang", callback_data=f"depomatur:extend:{deposit_id}"),
            InlineKeyboardButton("💰 Cairkan", callback_data=f"depomatur:withdraw:{deposit_id}"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)