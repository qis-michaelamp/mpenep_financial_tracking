import type { CategoryBreakdownItem } from "@/lib/recap";

// Kategori-warna dari palet kategorikal tetap (lihat app/globals.css --series-1..8).
// Urutan fixed, gak boleh di-generate/cycle -> itu yang bikin CVD-safe.
const SERIES_SLOTS = [
  "var(--series-1)",
  "var(--series-2)",
  "var(--series-3)",
  "var(--series-4)",
  "var(--series-5)",
  "var(--series-6)",
  "var(--series-7)",
  "var(--series-8)",
];

const MAX_CATEGORICAL_SLOTS = SERIES_SLOTS.length;

export type ColoredCategoryItem = CategoryBreakdownItem & { color: string };

/**
 * Assign warna kategorikal tetap ke tiap item (harus sudah di-sort desc by value).
 * Item ke-9 dst di-fold jadi 1 slot "Lainnya" warna abu-abu, bukan generate hue baru
 * (generated hue ke-9 gak bisa dibedain dari yang lain di bawah CVD).
 */
export function assignCategoryColors(
  items: CategoryBreakdownItem[],
  otherLabel = "Lainnya"
): ColoredCategoryItem[] {
  if (items.length <= MAX_CATEGORICAL_SLOTS) {
    return items.map((item, i) => ({ ...item, color: SERIES_SLOTS[i] }));
  }

  const head: ColoredCategoryItem[] = items
    .slice(0, MAX_CATEGORICAL_SLOTS - 1)
    .map((item, i) => ({ ...item, color: SERIES_SLOTS[i] }));

  const tail = items.slice(MAX_CATEGORICAL_SLOTS - 1);
  const otherTotal = tail.reduce((sum, item) => sum + item.total, 0);

  const other: ColoredCategoryItem = {
    categoryId: null,
    categoryName: otherLabel,
    icon: null,
    total: otherTotal,
    color: "var(--series-other)",
  };

  return [...head, other];
}
