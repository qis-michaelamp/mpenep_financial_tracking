import { formatRupiah } from "@/lib/format";

export default function SummaryCards({
  totalIncome,
  totalExpense,
  net,
}: {
  totalIncome: number;
  totalExpense: number;
  net: number;
}) {
  const cards = [
    { label: "Income", value: totalIncome, color: "text-emerald-600 dark:text-emerald-400" },
    { label: "Expense", value: totalExpense, color: "text-rose-600 dark:text-rose-400" },
    {
      label: "Net",
      value: net,
      color: net >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400",
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      {cards.map((card) => (
        <div
          key={card.label}
          className="rounded-xl border border-neutral-200 bg-white p-5 shadow-sm dark:border-neutral-800 dark:bg-neutral-900"
        >
          <p className="text-sm font-medium text-neutral-500 dark:text-neutral-400">{card.label}</p>
          <p className={`mt-1 text-2xl font-bold ${card.color}`}>{formatRupiah(card.value)}</p>
        </div>
      ))}
    </div>
  );
}
