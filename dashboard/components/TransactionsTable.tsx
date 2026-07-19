"use client";

import { useMemo, useState } from "react";
import { formatRupiah, dateLabel } from "@/lib/format";
import type { TransactionDetail } from "@/lib/recap";

const TYPE_ICON: Record<TransactionDetail["type"], string> = {
  expense: "💸",
  income: "💰",
  transfer: "🔄",
};

type GroupMode = "date" | "category";

function groupLabel(tx: TransactionDetail): string {
  if (tx.type === "transfer") return "🔄 Transfer";
  if (tx.categoryName) return tx.categoryIcon ? `${tx.categoryIcon} ${tx.categoryName}` : tx.categoryName;
  return "Tanpa Kategori";
}

// Transfer gak dihitung ke total group -> cuma perpindahan antar akun sendiri, sama kayak rekap bulanan.
function signedAmount(tx: TransactionDetail): number {
  if (tx.type === "income") return tx.amount;
  if (tx.type === "expense") return -tx.amount;
  return 0;
}

export default function TransactionsTable({ items }: { items: TransactionDetail[] }) {
  const [mode, setMode] = useState<GroupMode>("date");

  const groups = useMemo(() => {
    const map = new Map<string, TransactionDetail[]>();
    for (const tx of items) {
      const key = mode === "date" ? tx.transactionDate : groupLabel(tx);
      const arr = map.get(key);
      if (arr) arr.push(tx);
      else map.set(key, [tx]);
    }

    const entries = Array.from(map.entries());
    if (mode === "date") {
      entries.sort((a, b) => (a[0] < b[0] ? 1 : -1));
    } else {
      entries.sort((a, b) => {
        const totalA = a[1].reduce((sum, tx) => sum + Math.abs(signedAmount(tx)), 0);
        const totalB = b[1].reduce((sum, tx) => sum + Math.abs(signedAmount(tx)), 0);
        return totalB - totalA;
      });
    }
    return entries;
  }, [items, mode]);

  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-5 shadow-sm dark:border-neutral-800 dark:bg-neutral-900">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-semibold">Detail Transaksi</h2>
        <div className="flex gap-1 rounded-lg border border-neutral-300 p-0.5 text-sm dark:border-neutral-700">
          <button
            onClick={() => setMode("date")}
            className={`rounded-md px-3 py-1 transition-colors ${
              mode === "date"
                ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                : "text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100"
            }`}
          >
            Per Tanggal
          </button>
          <button
            onClick={() => setMode("category")}
            className={`rounded-md px-3 py-1 transition-colors ${
              mode === "category"
                ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                : "text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100"
            }`}
          >
            Per Kategori
          </button>
        </div>
      </div>

      {items.length === 0 ? (
        <p className="text-sm text-neutral-500 dark:text-neutral-400">Belum ada transaksi bulan ini.</p>
      ) : (
        <div className="flex flex-col gap-5">
          {groups.map(([key, txs]) => {
            const groupTotal = txs.reduce((sum, tx) => sum + signedAmount(tx), 0);
            return (
              <div key={key}>
                <div className="mb-2 flex items-center justify-between text-sm font-medium text-neutral-500 dark:text-neutral-400">
                  <span>{mode === "date" ? dateLabel(key) : key}</span>
                  {groupTotal !== 0 && (
                    <span className={groupTotal >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}>
                      {groupTotal >= 0 ? "+" : "-"}
                      {formatRupiah(Math.abs(groupTotal))}
                    </span>
                  )}
                </div>
                <table className="w-full text-sm">
                  <tbody>
                    {txs.map((tx) => (
                      <tr key={tx.id} className="border-t border-neutral-100 dark:border-neutral-800">
                        <td className="py-2 pr-2 text-neutral-400">
                          {mode === "date" ? groupLabel(tx) : dateLabel(tx.transactionDate)}
                        </td>
                        <td className="py-2 pr-2 text-neutral-600 dark:text-neutral-300">
                          {tx.type === "transfer"
                            ? `${tx.description || "Transfer"} (${tx.accountName} → ${tx.toAccountName ?? "?"})`
                            : `${tx.description || ""} (${tx.accountName})`}
                        </td>
                        <td className="py-2 text-right font-medium whitespace-nowrap">
                          {TYPE_ICON[tx.type]} {formatRupiah(tx.amount)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
