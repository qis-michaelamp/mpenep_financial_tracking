"""
Wrapper untuk semua operasi ke Supabase.
Pakai service_role key karena bot jalan di server-side (bypass RLS),
validasi akses dilakukan manual lewat whitelist telegram_chat_id di family_members.

PENTING: service_role key HARUS di env variable, jangan pernah hardcode.
"""

import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from supabase import create_client, Client

# Cache client biar koneksi (TLS handshake, connection pool) di-reuse,
# bukan bikin baru tiap fungsi dipanggil -> ini penyebab utama bot kerasa lambat,
# karena 1 interaksi bisa manggil beberapa fungsi Supabase sekaligus.
_client: Optional[Client] = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        _client = create_client(url, key)
    return _client


@dataclass
class FamilyMember:
    id: str
    family_id: str
    name: str
    role: str


@dataclass
class Account:
    id: str
    name: str
    type: str
    initial_balance: float


@dataclass
class Category:
    id: str
    name: str
    type: str
    icon: Optional[str]


@dataclass
class Installment:
    id: str
    family_id: str
    obligation_type: str
    name: str
    credit_card_id: Optional[str]
    funding_account_id: str
    category_id: Optional[str]
    amount_per_month: float
    billing_day: int
    tenor_months: Optional[int]
    months_paid: int
    interest_rate_pct: Optional[float]
    last_charged_month: Optional[str]
    status: str


@dataclass
class Deposit:
    id: str
    family_id: str
    name: str
    principal_amount: float
    interest_rate_pct_pa: float
    tenor_months: int
    start_date: str
    maturity_date: str
    account_id: Optional[str]
    status: str
    reminder_dismissed: bool
    interest_payment_day: Optional[int]
    interest_mode: Optional[str]
    receival_account_id: Optional[str]
    last_interest_month: Optional[str]


# ============================================
# FAMILY MEMBER
# ============================================

def get_member_by_chat_id(chat_id: int) -> Optional[FamilyMember]:
    """
    Cari anggota keluarga berdasarkan telegram_chat_id.
    Return None kalau chat_id gak terdaftar -> dipakai buat whitelist check.
    """
    client = get_client()
    res = (
        client.table("family_members")
        .select("id, family_id, name, role")
        .eq("telegram_chat_id", chat_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    row = res.data[0]
    return FamilyMember(
        id=row["id"], family_id=row["family_id"], name=row["name"], role=row["role"]
    )


def create_pending_member(family_id: str, name: str, role: str = "member") -> str:
    """
    Bikin anggota baru yang belum ke-link ke Telegram, dengan invite_code unik.
    Return invite_code yang di-generate, buat di-share manual ke orangnya.
    """
    import secrets

    # Charset tanpa karakter yang gampang keketuker (0/O, 1/I/l)
    charset = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    code = "".join(secrets.choice(charset) for _ in range(6))

    client = get_client()
    client.table("family_members").insert(
        {"family_id": family_id, "name": name, "role": role, "invite_code": code}
    ).execute()
    return code


def get_member_by_invite_code(code: str) -> Optional[FamilyMember]:
    """Cari member yang punya invite_code ini DAN belum ke-link ke chat_id manapun."""
    client = get_client()
    res = (
        client.table("family_members")
        .select("id, family_id, name, role")
        .eq("invite_code", code)
        .is_("telegram_chat_id", "null")
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    row = res.data[0]
    return FamilyMember(
        id=row["id"], family_id=row["family_id"], name=row["name"], role=row["role"]
    )


def register_member_chat_id(member_id: str, chat_id: int) -> None:
    """Link member ke chat_id Telegram-nya, invite_code dihapus (single-use)."""
    client = get_client()
    client.table("family_members").update(
        {"telegram_chat_id": chat_id, "invite_code": None}
    ).eq("id", member_id).execute()


def get_family_member_chat_ids(family_id: str) -> list[int]:
    """Ambil semua chat_id anggota keluarga yang udah terdaftar -> dipakai buat broadcast reminder."""
    client = get_client()
    res = (
        client.table("family_members")
        .select("telegram_chat_id")
        .eq("family_id", family_id)
        .not_.is_("telegram_chat_id", "null")
        .execute()
    )
    return [r["telegram_chat_id"] for r in res.data]


# ============================================
# INSTALLMENTS (cicilan kartu kredit & KPR)
# ============================================

def _row_to_installment(r: dict) -> Installment:
    return Installment(
        id=r["id"],
        family_id=r["family_id"],
        obligation_type=r["obligation_type"],
        name=r["name"],
        credit_card_id=r.get("credit_card_id"),
        funding_account_id=r["funding_account_id"],
        category_id=r.get("category_id"),
        amount_per_month=float(r["amount_per_month"]),
        billing_day=r["billing_day"],
        tenor_months=r.get("tenor_months"),
        months_paid=r["months_paid"],
        interest_rate_pct=float(r["interest_rate_pct"]) if r.get("interest_rate_pct") is not None else None,
        last_charged_month=r.get("last_charged_month"),
        status=r["status"],
    )


def create_installment(
    family_id: str,
    obligation_type: str,
    name: str,
    funding_account_id: str,
    amount_per_month: float,
    billing_day: int,
    category_id: Optional[str] = None,
    credit_card_id: Optional[str] = None,
    tenor_months: Optional[int] = None,
    interest_rate_pct: Optional[float] = None,
) -> str:
    client = get_client()
    res = (
        client.table("installments")
        .insert(
            {
                "family_id": family_id,
                "obligation_type": obligation_type,
                "name": name,
                "funding_account_id": funding_account_id,
                "category_id": category_id,
                "credit_card_id": credit_card_id,
                "amount_per_month": amount_per_month,
                "billing_day": billing_day,
                "tenor_months": tenor_months,
                "interest_rate_pct": interest_rate_pct,
            }
        )
        .execute()
    )
    return res.data[0]["id"]


def get_active_installments(family_id: str) -> list[Installment]:
    client = get_client()
    res = (
        client.table("installments")
        .select("*")
        .eq("family_id", family_id)
        .eq("status", "active")
        .order("billing_day")
        .execute()
    )
    return [_row_to_installment(r) for r in res.data]


def get_installment_by_id(installment_id: str) -> Optional[Installment]:
    client = get_client()
    res = client.table("installments").select("*").eq("id", installment_id).limit(1).execute()
    if not res.data:
        return None
    return _row_to_installment(res.data[0])


def get_installments_due_today_all_families(today_day: int, current_month: str) -> list[Installment]:
    """
    Dipakai CRON: cari SEMUA cicilan aktif lintas keluarga yang jatuh tempo hari ini
    dan belum di-charge bulan ini. current_month format 'YYYY-MM'.
    """
    client = get_client()
    res = (
        client.table("installments")
        .select("*")
        .eq("status", "active")
        .eq("billing_day", today_day)
        .execute()
    )
    result = []
    for r in res.data:
        if r.get("last_charged_month") != current_month:
            result.append(_row_to_installment(r))
    return result


def update_installment_interest_rate(installment_id: str, rate_pct: float) -> None:
    client = get_client()
    client.table("installments").update({"interest_rate_pct": rate_pct}).eq("id", installment_id).execute()


def mark_installment_charged(installment_id: str, current_month: str, completed: bool = False) -> None:
    """Update setelah reminder di-konfirmasi bayar ATAU di-skip -> cegah reminder dobel bulan ini."""
    client = get_client()
    payload = {"last_charged_month": current_month}
    if completed:
        payload["status"] = "completed"
    client.table("installments").update(payload).eq("id", installment_id).execute()


def increment_installment_months_paid(installment_id: str) -> int:
    """Return months_paid yang baru, dipakai buat cek udah lunas belum."""
    client = get_client()
    current = client.table("installments").select("months_paid").eq("id", installment_id).single().execute()
    new_count = current.data["months_paid"] + 1
    client.table("installments").update({"months_paid": new_count}).eq("id", installment_id).execute()
    return new_count


# ============================================
# DEPOSITS
# ============================================

def _row_to_deposit(r: dict) -> Deposit:
    return Deposit(
        id=r["id"],
        family_id=r["family_id"],
        name=r["name"],
        principal_amount=float(r["principal_amount"]),
        interest_rate_pct_pa=float(r["interest_rate_pct_pa"]),
        tenor_months=r["tenor_months"],
        start_date=r["start_date"],
        maturity_date=r["maturity_date"],
        account_id=r.get("account_id"),
        status=r["status"],
        reminder_dismissed=r["reminder_dismissed"],
        interest_payment_day=r.get("interest_payment_day"),
        interest_mode=r.get("interest_mode"),
        receival_account_id=r.get("receival_account_id"),
        last_interest_month=r.get("last_interest_month"),
    )


def create_deposit(
    family_id: str,
    name: str,
    principal_amount: float,
    interest_rate_pct_pa: float,
    tenor_months: int,
    maturity_date: date,
    account_id: Optional[str] = None,
    interest_payment_day: Optional[int] = None,
    interest_mode: Optional[str] = None,
    receival_account_id: Optional[str] = None,
) -> str:
    client = get_client()
    res = (
        client.table("deposits")
        .insert(
            {
                "family_id": family_id,
                "name": name,
                "principal_amount": principal_amount,
                "interest_rate_pct_pa": interest_rate_pct_pa,
                "tenor_months": tenor_months,
                "maturity_date": maturity_date.isoformat(),
                "account_id": account_id,
                "interest_payment_day": interest_payment_day,
                "interest_mode": interest_mode,
                "receival_account_id": receival_account_id,
            }
        )
        .execute()
    )
    return res.data[0]["id"]


def get_active_deposits(family_id: str) -> list[Deposit]:
    client = get_client()
    res = (
        client.table("deposits")
        .select("*")
        .eq("family_id", family_id)
        .eq("status", "active")
        .order("maturity_date")
        .execute()
    )
    return [_row_to_deposit(r) for r in res.data]


def get_deposit_by_id(deposit_id: str) -> Optional[Deposit]:
    client = get_client()
    res = client.table("deposits").select("*").eq("id", deposit_id).limit(1).execute()
    if not res.data:
        return None
    return _row_to_deposit(res.data[0])


def get_deposits_near_maturity_all_families(today: date, days_ahead: int = 3) -> list[Deposit]:
    """Dipakai CRON: deposito aktif yang maturity_date-nya dalam range [today, today+days_ahead]."""
    client = get_client()
    end_date = today + timedelta(days=days_ahead)
    res = (
        client.table("deposits")
        .select("*")
        .eq("status", "active")
        .gte("maturity_date", today.isoformat())
        .lte("maturity_date", end_date.isoformat())
        .execute()
    )
    return [_row_to_deposit(r) for r in res.data]


def dismiss_deposit_reminder(deposit_id: str) -> None:
    client = get_client()
    client.table("deposits").update({"reminder_dismissed": True}).eq("id", deposit_id).execute()


def update_deposit_status(deposit_id: str, status: str) -> None:
    """status: 'matured' | 'withdrawn' | 'extended'"""
    client = get_client()
    client.table("deposits").update({"status": status}).eq("id", deposit_id).execute()


def rollover_deposit(deposit_id: str, new_principal: float, new_maturity_date: date) -> None:
    """
    Perpanjang deposito dengan pokok baru (pokok lama + bunga yang udah didapet),
    reset reminder_dismissed biar reminder aktif lagi buat siklus berikutnya.
    """
    client = get_client()
    client.table("deposits").update(
        {
            "principal_amount": new_principal,
            "maturity_date": new_maturity_date.isoformat(),
            "status": "active",
            "reminder_dismissed": False,
        }
    ).eq("id", deposit_id).execute()


def get_deposits_with_monthly_interest_due_today_all_families(
    today_day: int, current_month: str
) -> list[Deposit]:
    """Dipakai CRON: deposito dengan bunga bulanan yang jatuh tempo cair hari ini."""
    client = get_client()
    res = (
        client.table("deposits")
        .select("*")
        .eq("status", "active")
        .eq("interest_payment_day", today_day)
        .not_.is_("interest_mode", "null")
        .execute()
    )
    result = []
    for r in res.data:
        if r.get("last_interest_month") != current_month:
            result.append(_row_to_deposit(r))
    return result


def update_deposit_last_interest_month(deposit_id: str, current_month: str) -> None:
    client = get_client()
    client.table("deposits").update({"last_interest_month": current_month}).eq("id", deposit_id).execute()


def credit_deposit_interest_rollover(deposit_id: str, interest_amount: float, current_month: str) -> None:
    """Bunga bulanan mode rollover: langsung nambah ke principal_amount, otomatis tanpa konfirmasi."""
    client = get_client()
    current = client.table("deposits").select("principal_amount").eq("id", deposit_id).single().execute()
    new_principal = float(current.data["principal_amount"]) + interest_amount
    client.table("deposits").update(
        {"principal_amount": new_principal, "last_interest_month": current_month}
    ).eq("id", deposit_id).execute()


# ============================================
# ACCOUNTS
# ============================================

def get_accounts(family_id: str) -> list[Account]:
    client = get_client()
    res = (
        client.table("accounts")
        .select("id, name, type, initial_balance")
        .eq("family_id", family_id)
        .order("name")
        .execute()
    )
    return [
        Account(
            id=r["id"],
            name=r["name"],
            type=r["type"],
            initial_balance=float(r["initial_balance"]),
        )
        for r in res.data
    ]


def create_account(family_id: str, name: str, type: str, initial_balance: float = 0) -> str:
    """Bikin akun baru, return id-nya."""
    client = get_client()
    res = (
        client.table("accounts")
        .insert({"family_id": family_id, "name": name, "type": type, "initial_balance": initial_balance})
        .execute()
    )
    return res.data[0]["id"]


def account_has_dependencies(account_id: str) -> bool:
    """
    Cek apakah akun ini udah dipakai di transaksi/cicilan -> kalau iya, gak boleh dihapus
    biar riwayat data gak jadi rusak (nyantol ke akun yang udah gak ada).
    """
    client = get_client()
    tx = (
        client.table("transactions")
        .select("id")
        .or_(f"account_id.eq.{account_id},to_account_id.eq.{account_id}")
        .limit(1)
        .execute()
    )
    if tx.data:
        return True
    inst = (
        client.table("installments")
        .select("id")
        .eq("funding_account_id", account_id)
        .limit(1)
        .execute()
    )
    return bool(inst.data)


def delete_account(account_id: str) -> None:
    client = get_client()
    client.table("accounts").delete().eq("id", account_id).execute()


def get_account_balance(account_id: str) -> float:
    """
    Hitung saldo real-time: initial_balance + agregat transaksi yang menyentuh akun ini.
    - expense di akun ini -> kurangi
    - income di akun ini -> tambah
    - transfer KELUAR dari akun ini (account_id) -> kurangi
    - transfer MASUK ke akun ini (to_account_id) -> tambah
    """
    client = get_client()

    account_res = (
        client.table("accounts")
        .select("initial_balance")
        .eq("id", account_id)
        .single()
        .execute()
    )
    balance = float(account_res.data["initial_balance"])

    # Transaksi dimana akun ini jadi account_id (sumber)
    tx_out = (
        client.table("transactions")
        .select("type, amount")
        .eq("account_id", account_id)
        .execute()
    )
    for tx in tx_out.data:
        if tx["type"] == "income":
            balance += float(tx["amount"])
        elif tx["type"] in ("expense", "transfer"):
            balance -= float(tx["amount"])

    # Transaksi dimana akun ini jadi to_account_id (tujuan transfer)
    tx_in = (
        client.table("transactions")
        .select("amount")
        .eq("to_account_id", account_id)
        .execute()
    )
    for tx in tx_in.data:
        balance += float(tx["amount"])

    return balance


# ============================================
# CATEGORIES
# ============================================

def get_categories(family_id: str, type: str) -> list[Category]:
    """type: 'income' atau 'expense'"""
    client = get_client()
    res = (
        client.table("categories")
        .select("id, name, type, icon")
        .eq("family_id", family_id)
        .eq("type", type)
        .order("name")
        .execute()
    )
    return [
        Category(id=r["id"], name=r["name"], type=r["type"], icon=r.get("icon"))
        for r in res.data
    ]


# ============================================
# TRANSACTIONS
# ============================================

def insert_transaction(
    family_id: str,
    member_id: str,
    type: str,  # 'income' | 'expense' | 'transfer'
    account_id: str,
    amount: float,
    description: str,
    transaction_date: date,
    category_id: Optional[str] = None,
    to_account_id: Optional[str] = None,
    source: str = "telegram",
) -> str:
    """Insert transaksi baru, return id transaksi yang baru dibuat."""
    client = get_client()
    payload = {
        "family_id": family_id,
        "member_id": member_id,
        "type": type,
        "account_id": account_id,
        "amount": amount,
        "description": description,
        "transaction_date": transaction_date.isoformat(),
        "category_id": category_id,
        "to_account_id": to_account_id,
        "source": source,
    }
    res = client.table("transactions").insert(payload).execute()
    return res.data[0]["id"]


def get_recent_transactions(family_id: str, limit: int = 10) -> list[dict]:
    """Ambil transaksi terakhir buat /riwayat, join manual ke nama kategori & akun."""
    client = get_client()
    res = (
        client.table("transactions")
        .select(
            "id, type, amount, description, transaction_date, "
            "accounts:account_id(name), "
            "to_accounts:to_account_id(name), "
            "categories:category_id(name, icon)"
        )
        .eq("family_id", family_id)
        .order("transaction_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data


def delete_transaction(transaction_id: str) -> None:
    """Dipakai buat fitur batalkan/hapus transaksi terakhir."""
    client = get_client()
    client.table("transactions").delete().eq("id", transaction_id).execute()


def update_account_initial_balance(account_id: str, amount: float) -> None:
    """Set ulang saldo awal akun -> dipakai buat inisialisasi/koreksi modal awal."""
    client = get_client()
    client.table("accounts").update({"initial_balance": amount}).eq("id", account_id).execute()


def get_account_by_id(account_id: str) -> Optional[Account]:
    client = get_client()
    res = (
        client.table("accounts")
        .select("id, name, type, initial_balance")
        .eq("id", account_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    r = res.data[0]
    return Account(id=r["id"], name=r["name"], type=r["type"], initial_balance=float(r["initial_balance"]))


def get_category_by_id(category_id: str) -> Optional[Category]:
    client = get_client()
    res = (
        client.table("categories")
        .select("id, name, type, icon")
        .eq("id", category_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    r = res.data[0]
    return Category(id=r["id"], name=r["name"], type=r["type"], icon=r.get("icon"))


# ============================================
# BOT SESSION (draft transaksi multi-step)
# Wajib ada karena Vercel serverless stateless -> gak bisa simpen
# progress percakapan di memory Python antar request.
# ============================================

def get_session(chat_id: int) -> dict:
    """Ambil draft transaksi yang lagi jalan. Return {} kalau belum ada sesi."""
    client = get_client()
    res = (
        client.table("bot_sessions")
        .select("draft")
        .eq("chat_id", chat_id)
        .execute()
    )
    if not res.data:
        return {}
    return res.data[0]["draft"] or {}


def save_session(chat_id: int, draft: dict) -> None:
    """Simpan/update draft transaksi (upsert berdasarkan chat_id)."""
    client = get_client()
    client.table("bot_sessions").upsert(
        {"chat_id": chat_id, "draft": draft}
    ).execute()


def clear_session(chat_id: int) -> None:
    """Hapus draft setelah transaksi disimpan/dibatalkan."""
    client = get_client()
    client.table("bot_sessions").delete().eq("chat_id", chat_id).execute()