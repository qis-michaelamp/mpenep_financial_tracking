"use client";

import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { formatRupiah } from "@/lib/format";
import { assignCategoryColors } from "@/lib/palette";
import type { CategoryBreakdownItem } from "@/lib/recap";

export default function ExpenseDonut({ items }: { items: CategoryBreakdownItem[] }) {
  if (items.length === 0) {
    return null;
  }

  const colored = assignCategoryColors(items);
  const total = colored.reduce((sum, item) => sum + item.total, 0);
  const chartData = colored.map((item) => ({
    name: item.icon ? `${item.icon} ${item.categoryName}` : item.categoryName,
    value: item.total,
    color: item.color,
  }));

  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-5 shadow-sm dark:border-neutral-800 dark:bg-neutral-900">
      <h2 className="mb-4 text-base font-semibold">Proporsi Expense per Kategori</h2>

      <div style={{ width: "100%", height: 280 }}>
        <ResponsiveContainer>
          <PieChart>
            <Pie
              data={chartData}
              dataKey="value"
              nameKey="name"
              innerRadius="55%"
              outerRadius="80%"
              paddingAngle={2}
              stroke="var(--chart-surface)"
              strokeWidth={2}
            >
              {chartData.map((entry, i) => (
                <Cell key={i} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              formatter={(value) => {
                const num = Number(value);
                return [`${formatRupiah(num)} (${((num / total) * 100).toFixed(1)}%)`, ""];
              }}
              contentStyle={{
                background: "var(--chart-surface)",
                border: "1px solid var(--chart-grid)",
                borderRadius: 8,
                fontSize: 13,
              }}
            />
            <Legend
              layout="vertical"
              align="right"
              verticalAlign="middle"
              wrapperStyle={{ fontSize: 12 }}
              formatter={(value) => <span style={{ color: "var(--foreground)" }}>{value}</span>}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
