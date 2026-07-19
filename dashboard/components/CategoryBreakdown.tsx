"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatRupiah } from "@/lib/format";
import type { CategoryBreakdownItem } from "@/lib/recap";

export default function CategoryBreakdown({
  title,
  items,
  barColor,
}: {
  title: string;
  items: CategoryBreakdownItem[];
  barColor: string;
}) {
  const chartData = items.map((item) => ({
    name: item.icon ? `${item.icon} ${item.categoryName}` : item.categoryName,
    total: item.total,
  }));

  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-5 shadow-sm dark:border-neutral-800 dark:bg-neutral-900">
      <h2 className="mb-4 text-base font-semibold">{title}</h2>

      {items.length === 0 ? (
        <p className="text-sm text-neutral-500 dark:text-neutral-400">Belum ada transaksi bulan ini.</p>
      ) : (
        <>
          <div style={{ width: "100%", height: Math.max(items.length * 40, 120) }}>
            <ResponsiveContainer>
              <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 24 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" tickFormatter={(v) => formatRupiah(v)} fontSize={12} />
                <YAxis type="category" dataKey="name" width={140} fontSize={12} />
                <Tooltip formatter={(value) => formatRupiah(Number(value))} />
                <Bar dataKey="total" fill={barColor} radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <table className="mt-4 w-full text-sm">
            <tbody>
              {items.map((item) => (
                <tr
                  key={item.categoryId ?? "none"}
                  className="border-t border-neutral-100 dark:border-neutral-800"
                >
                  <td className="py-2 text-neutral-600 dark:text-neutral-300">
                    {item.icon ? `${item.icon} ` : ""}
                    {item.categoryName}
                  </td>
                  <td className="py-2 text-right font-medium">{formatRupiah(item.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
