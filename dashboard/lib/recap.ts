import type { SupabaseClient } from "@supabase/supabase-js";

export type CategoryBreakdownItem = {
  categoryId: string | null;
  categoryName: string;
  icon: string | null;
  total: number;
};

export type RecapData = {
  totalIncome: number;
  totalExpense: number;
  net: number;
  incomeByCategory: CategoryBreakdownItem[];
  expenseByCategory: CategoryBreakdownItem[];
};

type TransactionRow = {
  type: "income" | "expense" | "transfer";
  amount: number;
  category_id: string | null;
  categories: { name: string; icon: string | null } | null;
};

/**
 * Range bulan [start, end) dari string "YYYY-MM".
 */
function monthRange(monthStr: string): { start: string; end: string } {
  const [year, month] = monthStr.split("-").map(Number);
  const start = new Date(year, month - 1, 1);
  const end = new Date(year, month, 1);
  const toIso = (d: Date) => d.toISOString().slice(0, 10);
  return { start: toIso(start), end: toIso(end) };
}

function groupByCategory(rows: TransactionRow[]): CategoryBreakdownItem[] {
  const map = new Map<string, CategoryBreakdownItem>();

  for (const row of rows) {
    const key = row.category_id ?? "none";
    const existing = map.get(key);
    if (existing) {
      existing.total += Number(row.amount);
    } else {
      map.set(key, {
        categoryId: row.category_id,
        categoryName: row.categories?.name ?? "Tanpa kategori",
        icon: row.categories?.icon ?? null,
        total: Number(row.amount),
      });
    }
  }

  return Array.from(map.values()).sort((a, b) => b.total - a.total);
}

export type MonthlyTrendItem = {
  month: string; // "YYYY-MM"
  income: number;
  expense: number;
};

/**
 * Ambil total income & expense per bulan, dari (endMonth - monthsBack + 1) s/d endMonth.
 * Dipakai buat trend chart -> 1 query range, di-bucket per bulan di client.
 */
export async function getMonthlyTrend(
  supabase: SupabaseClient,
  endMonth: string,
  monthsBack: number
): Promise<MonthlyTrendItem[]> {
  const [endYear, endMonthNum] = endMonth.split("-").map(Number);
  const startDate = new Date(endYear, endMonthNum - 1 - (monthsBack - 1), 1);
  const startMonth = `${startDate.getFullYear()}-${String(startDate.getMonth() + 1).padStart(2, "0")}`;

  const { start } = monthRange(startMonth);
  const { end } = monthRange(endMonth);

  const { data, error } = await supabase
    .from("transactions")
    .select("type, amount, transaction_date")
    .gte("transaction_date", start)
    .lt("transaction_date", end)
    .neq("type", "transfer")
    .returns<{ type: "income" | "expense" | "transfer"; amount: number; transaction_date: string }[]>();

  if (error) {
    throw new Error(`Gagal ambil data trend: ${error.message}`);
  }

  // Siapkan bucket kosong dulu buat semua bulan di range -> bulan tanpa transaksi tetap muncul sebagai 0
  const buckets = new Map<string, MonthlyTrendItem>();
  for (let i = 0; i < monthsBack; i++) {
    const d = new Date(startDate.getFullYear(), startDate.getMonth() + i, 1);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    buckets.set(key, { month: key, income: 0, expense: 0 });
  }

  for (const row of data ?? []) {
    const key = row.transaction_date.slice(0, 7);
    const bucket = buckets.get(key);
    if (!bucket) continue;
    if (row.type === "income") bucket.income += Number(row.amount);
    else if (row.type === "expense") bucket.expense += Number(row.amount);
  }

  return Array.from(buckets.values());
}

/**
 * Ambil & agregasi transaksi 1 bulan. Transfer di-exclude dari income/expense
 * karena itu cuma perpindahan uang antar akun sendiri, bukan uang masuk/keluar
 * beneran (sesuai keputusan scope rekap ini).
 */
export async function getRecapForMonth(
  supabase: SupabaseClient,
  monthStr: string
): Promise<RecapData> {
  const { start, end } = monthRange(monthStr);

  const { data, error } = await supabase
    .from("transactions")
    .select("type, amount, category_id, categories:category_id(name, icon)")
    .gte("transaction_date", start)
    .lt("transaction_date", end)
    .neq("type", "transfer")
    .returns<TransactionRow[]>();

  if (error) {
    throw new Error(`Gagal ambil data transaksi: ${error.message}`);
  }

  const rows = data ?? [];
  const incomeRows = rows.filter((r) => r.type === "income");
  const expenseRows = rows.filter((r) => r.type === "expense");

  const totalIncome = incomeRows.reduce((sum, r) => sum + Number(r.amount), 0);
  const totalExpense = expenseRows.reduce((sum, r) => sum + Number(r.amount), 0);

  return {
    totalIncome,
    totalExpense,
    net: totalIncome - totalExpense,
    incomeByCategory: groupByCategory(incomeRows),
    expenseByCategory: groupByCategory(expenseRows),
  };
}

export type TransactionDetail = {
  id: string;
  type: "income" | "expense" | "transfer";
  amount: number;
  description: string | null;
  transactionDate: string;
  categoryName: string | null;
  categoryIcon: string | null;
  accountName: string;
  toAccountName: string | null;
};

type TransactionDetailRow = {
  id: string;
  type: "income" | "expense" | "transfer";
  amount: number;
  description: string | null;
  transaction_date: string;
  accounts: { name: string } | null;
  to_accounts: { name: string } | null;
  categories: { name: string; icon: string | null } | null;
};

/**
 * Ambil detail transaksi 1 bulan (semua tipe, termasuk transfer) buat tabel rekap
 * yang bisa di-group per tanggal atau per kategori di client.
 */
export async function getTransactionsForMonth(
  supabase: SupabaseClient,
  monthStr: string
): Promise<TransactionDetail[]> {
  const { start, end } = monthRange(monthStr);

  const { data, error } = await supabase
    .from("transactions")
    .select(
      "id, type, amount, description, transaction_date, " +
        "accounts:account_id(name), to_accounts:to_account_id(name), categories:category_id(name, icon)"
    )
    .gte("transaction_date", start)
    .lt("transaction_date", end)
    .order("transaction_date", { ascending: false })
    .returns<TransactionDetailRow[]>();

  if (error) {
    throw new Error(`Gagal ambil detail transaksi: ${error.message}`);
  }

  return (data ?? []).map((r) => ({
    id: r.id,
    type: r.type,
    amount: Number(r.amount),
    description: r.description,
    transactionDate: r.transaction_date,
    categoryName: r.categories?.name ?? null,
    categoryIcon: r.categories?.icon ?? null,
    accountName: r.accounts?.name ?? "?",
    toAccountName: r.to_accounts?.name ?? null,
  }));
}
