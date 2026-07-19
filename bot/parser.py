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

# Pattern: angka (boleh ada . atau , sbg desimal/pemisah, BOLEH BERULANG buat
# pemisah ribuan multi-grup) + optional suffix
# Contoh yang harus match: 25000 | 25rb | 25 rb | 25.000 | 7.5jt | 12,500 | 10.000.000,57
# Alternatif 1: 1-3 digit diikuti >=1 grup 3-digit (pemisah ribuan berulang),
#   opsional diakhiri 1 grup 1-2 digit (desimal/sen) -> nangkep "10.000.000,57" sebagai 1 token utuh
# Alternatif 2 (fallback lama): digit + opsional 1 grup pemisah bebas panjang -> nangkep "7.5jt", "25,5rb"
NUMBER_PATTERN = re.compile(
    r"(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d+)?)\s*(juta|jt|ribu|rb|k)?\b",
    re.IGNORECASE,
)

# Threshold minimum: angka polos tanpa suffix di bawah ini dianggap BUKAN nominal
# (misal biar "quantity 2 porsi" gak ke-detect sebagai transaksi Rp2)
MIN_BARE_NUMBER = 100


def _normalize_number(raw_number: str, suffix: Optional[str]) -> float:
    """Ubah string angka mentah (boleh multi pemisah ribuan) + suffix jadi float nominal rupiah."""
    raw_number = raw_number.strip()
    multiplier = MULTIPLIERS[suffix.lower()] if suffix else 1

    parts = re.split(r"[.,]", raw_number)
    if len(parts) == 1:
        return float(parts[0]) * multiplier

    *thousand_groups, last_part = parts

    # Grup terakhir 3 digit (dan semua grup sebelumnya juga <=3 digit) -> semua
    # pemisah adalah ribuan, gabungkan apa adanya (misal "10.000.000" -> 10000000)
    if len(last_part) == 3 and all(len(p) <= 3 for p in thousand_groups):
        return float("".join(parts)) * multiplier

    # Grup terakhir 1-2 digit -> itu desimal/sen, sisanya pemisah ribuan
    # (misal "10.000.000,57" -> 10000000.57 ; "7.5jt" -> 7.5 * 1_000_000)
    integer_part = "".join(thousand_groups)
    return float(f"{integer_part}.{last_part}") * multiplier


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