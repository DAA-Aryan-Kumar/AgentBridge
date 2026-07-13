-- AgentBridge Supabase schema (R23) — one-time setup.
-- Paste into the dashboard SQL editor (project > SQL) and Run.
--
-- Trust model v1: RLS is ENABLED with NO policies, so the publishable key
-- can touch nothing; only the service (secret) key — held by the app on the
-- member's machine — can read/write. Per-member Supabase auth with real RLS
-- policies is a later round. E2EE is unchanged either way: message bodies
-- and files arrive here already sealed (the server only stores ciphertext).

-- JSON documents (meta snapshots, accounts, status docs, overlays…)
create table if not exists public.ab_docs (
  root    text not null,
  path    text not null,
  data    jsonb not null,
  updated timestamptz not null default now(),
  primary key (root, path)
);

-- Append-only message logs (one row per record; id = the read offset)
create table if not exists public.ab_logs (
  id       bigint generated always as identity primary key,
  root     text not null,
  chat_id  text not null,
  log_name text not null,
  line     text not null
);
create index if not exists ab_logs_scan
  on public.ab_logs (root, chat_id, log_name, id);

alter table public.ab_docs enable row level security;
alter table public.ab_logs enable row level security;
-- no policies on purpose: service key only (v1 trust model)

-- One round-trip helpers (PostgREST cannot group-by without an RPC)
create or replace function public.ab_list_logs(p_root text, p_chat text)
returns table (log_name text, head bigint)
language sql stable as $$
  select log_name, max(id) as head
  from public.ab_logs
  where root = p_root and chat_id = p_chat
  group by log_name
$$;

create or replace function public.ab_chat_ids(p_root text)
returns table (chat_id text)
language sql stable as $$
  select distinct chat_id from public.ab_logs where root = p_root
  union
  select distinct split_part(path, '/', 2)
  from public.ab_docs
  where root = p_root and path like 'chats/%'
$$;

-- Storage: the app creates the private bucket itself ("ab-mesh").
