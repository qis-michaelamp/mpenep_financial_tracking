-- ============================================
-- TAMBAHAN: bot_sessions
-- Nyimpen progress transaksi yang lagi "dalam proses" per chat_id,
-- karena Vercel serverless stateless -> gak bisa simpen di memory Python.
-- Jalankan ini di SQL Editor Supabase (tambahan dari schema.sql sebelumnya)
-- ============================================

create table bot_sessions (
  chat_id bigint primary key,
  draft jsonb not null default '{}'::jsonb,  -- {amount, description, type, category_id, account_id, to_account_id, date}
  updated_at timestamptz not null default now()
);

-- RLS: cuma service_role yang boleh akses tabel ini (bot doang, gak ada user login yang akses)
alter table bot_sessions enable row level security;
-- Sengaja TIDAK bikin policy select/insert untuk anon/authenticated -> otomatis semua tertolak
-- kecuali lewat service_role key (yang bypass RLS). Ini isolasi tabel operasional dari akses publik.
