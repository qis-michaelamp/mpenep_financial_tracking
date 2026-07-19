// Format currency konsisten dengan bot Telegram (bot/handlers.py):
// f"Rp{amount:,.0f}".replace(",", ".") -> "Rp1.234.567"
export function formatRupiah(amount: number): string {
  const rounded = Math.round(amount);
  return "Rp" + rounded.toLocaleString("en-US").replace(/,/g, ".");
}

export function monthLabel(monthStr: string): string {
  const [year, month] = monthStr.split("-").map(Number);
  const date = new Date(year, month - 1, 1);
  return date.toLocaleDateString("id-ID", { month: "long", year: "numeric" });
}

export function monthShortLabel(monthStr: string): string {
  const [year, month] = monthStr.split("-").map(Number);
  const date = new Date(year, month - 1, 1);
  return date.toLocaleDateString("id-ID", { month: "short", year: "2-digit" });
}

// Compact buat sumbu/label chart: 1.2jt, 850rb, dst -- gak perlu presisi rupiah penuh.
export function formatCompact(amount: number): string {
  const abs = Math.abs(amount);
  const sign = amount < 0 ? "-" : "";
  if (abs >= 1_000_000) return `${sign}${(abs / 1_000_000).toFixed(abs >= 10_000_000 ? 0 : 1)}jt`;
  if (abs >= 1_000) return `${sign}${(abs / 1_000).toFixed(abs >= 10_000 ? 0 : 1)}rb`;
  return `${sign}${abs}`;
}

export function currentMonthStr(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  return `${now.getFullYear()}-${month}`;
}
