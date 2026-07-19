import { createClient } from "@/lib/supabase/server";
import { getMonthlyTrend, getRecapForMonth } from "@/lib/recap";
import { currentMonthStr } from "@/lib/format";
import MonthPicker from "@/components/MonthPicker";
import SummaryCards from "@/components/SummaryCards";
import CategoryBreakdown from "@/components/CategoryBreakdown";
import MonthlyTrendChart from "@/components/MonthlyTrendChart";
import ExpenseDonut from "@/components/ExpenseDonut";
import LogoutButton from "@/components/LogoutButton";

const TREND_MONTHS = 6;

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ month?: string }>;
}) {
  const { month: monthParam } = await searchParams;
  const month = monthParam ?? currentMonthStr();

  const supabase = await createClient();
  const [recap, trend] = await Promise.all([
    getRecapForMonth(supabase, month),
    getMonthlyTrend(supabase, month, TREND_MONTHS),
  ]);

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-4 py-8">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Rekap Keuangan</h1>
        <LogoutButton />
      </header>

      <MonthPicker month={month} />

      <SummaryCards
        totalIncome={recap.totalIncome}
        totalExpense={recap.totalExpense}
        net={recap.net}
      />

      <MonthlyTrendChart data={trend} />

      <ExpenseDonut items={recap.expenseByCategory} />

      <CategoryBreakdown title="Expense per Kategori" items={recap.expenseByCategory} barColor="var(--chart-expense)" />
      <CategoryBreakdown title="Income per Kategori" items={recap.incomeByCategory} barColor="var(--chart-income)" />
    </div>
  );
}
