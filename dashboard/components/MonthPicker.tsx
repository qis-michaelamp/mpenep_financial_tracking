"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { monthLabel } from "@/lib/format";

function shiftMonth(monthStr: string, delta: number): string {
  const [year, month] = monthStr.split("-").map(Number);
  const date = new Date(year, month - 1 + delta, 1);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

export default function MonthPicker({ month }: { month: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();

  function goTo(newMonth: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("month", newMonth);
    router.push(`/?${params.toString()}`);
  }

  return (
    <div className="flex items-center justify-center gap-4">
      <button
        onClick={() => goTo(shiftMonth(month, -1))}
        className="rounded-lg border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
        aria-label="Bulan sebelumnya"
      >
        ←
      </button>
      <span className="min-w-[10rem] text-center text-lg font-semibold capitalize">
        {monthLabel(month)}
      </span>
      <button
        onClick={() => goTo(shiftMonth(month, 1))}
        className="rounded-lg border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
        aria-label="Bulan berikutnya"
      >
        →
      </button>
    </div>
  );
}
