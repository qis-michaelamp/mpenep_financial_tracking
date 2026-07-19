"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatCompact, formatRupiah, monthShortLabel } from "@/lib/format";
import type { MonthlyTrendItem } from "@/lib/recap";

export default function MonthlyTrendChart({ data }: { data: MonthlyTrendItem[] }) {
  const chartData = data.map((d) => ({
    month: monthShortLabel(d.month),
    Income: d.income,
    Expense: d.expense,
  }));

  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-5 shadow-sm dark:border-neutral-800 dark:bg-neutral-900">
      <h2 className="mb-4 text-base font-semibold">Tren Income vs Expense</h2>

      <div style={{ width: "100%", height: 260 }}>
        <ResponsiveContainer>
          <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="1 0" stroke="var(--chart-grid)" vertical={false} />
            <XAxis
              dataKey="month"
              tickLine={false}
              axisLine={{ stroke: "var(--chart-axis)" }}
              tick={{ fill: "var(--chart-text-muted)", fontSize: 12 }}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--chart-text-muted)", fontSize: 12 }}
              tickFormatter={(v) => formatCompact(v)}
              width={48}
            />
            <Tooltip
              formatter={(value) => formatRupiah(Number(value))}
              contentStyle={{
                background: "var(--chart-surface)",
                border: "1px solid var(--chart-grid)",
                borderRadius: 8,
                fontSize: 13,
              }}
            />
            <Legend
              wrapperStyle={{ fontSize: 13 }}
              formatter={(value) => <span style={{ color: "var(--foreground)" }}>{value}</span>}
            />
            <Line
              type="monotone"
              dataKey="Income"
              stroke="var(--chart-income)"
              strokeWidth={2}
              dot={{ r: 4, fill: "var(--chart-income)", stroke: "var(--chart-surface)", strokeWidth: 2 }}
              activeDot={{ r: 5 }}
            />
            <Line
              type="monotone"
              dataKey="Expense"
              stroke="var(--chart-expense)"
              strokeWidth={2}
              dot={{ r: 4, fill: "var(--chart-expense)", stroke: "var(--chart-surface)", strokeWidth: 2 }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
