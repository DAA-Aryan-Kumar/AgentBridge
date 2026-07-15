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

-- ---------------------------------------------------------------------------
-- R76 (V84, the egress round) — incremental doc sync. Idempotent; paste the
-- whole file again (or just this section) and Run. Until this lands the app
-- runs in a slower legacy full-snapshot mode and the Connection panel says so.
--
-- Every insert/update gets a globally monotonic `seq` from one sequence, so
-- "what changed since seq X?" is one indexed query (the docs twin of the
-- ab_logs id feed). Deletes become SOFT (deleted=true, seq bumped) so they
-- ride the same feed; the app purges old tombstones and heals via periodic
-- full reconciles.

alter table public.ab_docs add column if not exists seq bigint not null default 0;
alter table public.ab_docs add column if not exists deleted boolean not null default false;

create sequence if not exists public.ab_docs_ver;

create or replace function public.ab_docs_touch() returns trigger
language plpgsql as $$
begin
  new.seq := nextval('public.ab_docs_ver');
  new.updated := now();
  return new;
end $$;

drop trigger if exists ab_docs_touch on public.ab_docs;
create trigger ab_docs_touch before insert or update on public.ab_docs
  for each row execute function public.ab_docs_touch();

-- backfill: assign a seq to every pre-migration row (no-op update fires the
-- trigger; rerunning skips rows that already have one)
update public.ab_docs set deleted = deleted where seq = 0;

create index if not exists ab_docs_delta on public.ab_docs (root, seq);

-- tombstones must not resurrect chat ids in the listing helper
create or replace function public.ab_chat_ids(p_root text)
returns table (chat_id text)
language sql stable as $$
  select distinct chat_id from public.ab_logs where root = p_root
  union
  select distinct split_part(path, '/', 2)
  from public.ab_docs
  where root = p_root and path like 'chats/%' and not deleted
$$;
