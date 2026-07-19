"""
Parser untuk extract nominal uang dan deskripsi dari teks yang diketik user.
Contoh input yang harus bisa di-handle:
  "kopi 25000"       -> amount=25000, desc="kopi"
  "kopi 25rb"        -> amount=25000, desc="kopi"
  "kopi 25 ribu"     -> amount=25000, desc="kopi"
  "kopi 25k"         -> amount=25000, desc="kopi"
  "beli laptop 7.5jt"-> amount=7500000, desc="beli laptop"
  "makan 12.500"     -> amount=12500, desc="makan"  (titik sbg pemisah ribuan)
  "halo bot"         -> None (gak ada nominal terdeteksi)
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedTransaction:
    amount: float
    description: str
    raw_text: str


# Suffix pengali, urutan penting: cek yang lebih panjang dulu biar gak salah match
# (misal "ribu" harus dicek sebelum "rb" kalau overlap, walau di sini gak overlap)
MULTIPLIERS = {
    "juta": 1_000_000,
    "jt": 1_000_000,
    "ribu": 1_000,
    "rb": 1_000,
    "k": 1_000,
}

# Pattern: angka (boleh ada . atau , sbg desimal/pemisah) + optional suffix
# Contoh yang harus match: 25000 | 25rb | 25 rb | 25.000 | 7.5jt | 12,500
NUMBER_PATTERN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(juta|jt|ribu|rb|k)?\b",
    re.IGNORECASE,
)

# Threshold minimum: angka polos tanpa suffix di bawah ini dianggap BUKAN nominal
# (misal biar "quantity 2 porsi" gak ke-detect sebagai transaksi Rp2)
MIN_BARE_NUMBER = 100


def _normalize_number(raw_number: str, suffix: Optional[str]) -> float:
    """Ubah string angka mentah + suffix jadi float nominal rupiah."""
    raw_number = raw_number.strip()

    if suffix:
        # Ada suffix (rb/jt/k/dst) -> pemisah pasti desimal, bukan ribuan
        # "7.5jt" -> 7.5 * 1_000_000 ; "25,5rb" -> 25.5 * 1000
        normalized = raw_number.replace(",", ".")
        base = float(normalized)
        multiplier = MULTIPLIERS[suffix.lower()]
        return base * multiplier

    # Tanpa suffix -> perlu nebak apakah . / , itu pemisah ribuan atau desimal
    # Heuristik: kalau ada tepat 3 digit setelah pemisah TERAKHIR dan angka
    # sebelum pemisah <= 3 digit -> kemungkinan besar pemisah ribuan (25.000 / 12,500)
    # Kalau cuma 1-2 digit di belakang -> kemungkinan desimal (25.5 -> 25.5, jarang kejadian tanpa suffix)
    match = re.match(r"^(\d+)([.,])(\d+)$", raw_number)
    if match:
        integer_part, _, decimal_part = match.groups()
        if len(decimal_part) == 3:
            # pemisah ribuan, gabungkan tanpa titik/koma
            return float(integer_part + decimal_part)
        else:
            # anggap desimal beneran (jarang untuk kasus rupiah tanpa suffix)
            return float(integer_part + "." + decimal_part)

    return float(raw_number)


def parse_transaction_text(text: str) -> Optional[ParsedTransaction]:
    """
    Cari angka nominal dari teks, ambil yang PALING TERAKHIR muncul
    (asumsi: user biasa nulis "[item] [nominal]" di akhir kalimat).
    Sisa teks di luar match nominal dianggap deskripsi.
    """
    text = text.strip()
    if not text:
        return None

    matches = list(NUMBER_PATTERN.finditer(text))
    if not matches:
        return None

    # Ambil match terakhir yang valid sebagai nominal
    chosen = None
    for m in reversed(matches):
        raw_number, suffix = m.group(1), m.group(2)
        try:
            amount = _normalize_number(raw_number, suffix)
        except ValueError:
            continue

        # Kalau gak ada suffix dan angkanya kekecilan, skip (kemungkinan bukan nominal)
        if not suffix and amount < MIN_BARE_NUMBER:
            continue

        chosen = (m, amount)
        break

    if chosen is None:
        return None

    match_obj, amount = chosen

    # Deskripsi = teks di luar span match nominal, dirapikan
    description = (text[: match_obj.start()] + " " + text[match_obj.end() :]).strip()
    description = re.sub(r"\s+", " ", description).strip(" -.,")

    if not description:
        description = "Tanpa deskripsi"

    return ParsedTransaction(amount=amount, description=description, raw_text=text)


def parse_plain_amount(text: str) -> Optional[float]:
    """
    Parser nominal polos buat konteks NON-transaksi (saldo awal, cicilan, deposito).
    Beda dari parse_transaction_text: nerima 0, gak ada MIN_BARE_NUMBER,
    karena di konteks ini gak ada resiko salah tangkep angka acak dari kalimat bebas.
    """
    text = text.strip()
    if not text:
        return None

    match = NUMBER_PATTERN.search(text)
    if not match:
        return None

    raw_number, suffix = match.group(1), match.group(2)
    try:
        return _normalize_number(raw_number, suffix)
    except ValueError:
        return None