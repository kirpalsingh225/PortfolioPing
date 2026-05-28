create extension if not exists pgcrypto;

create table if not exists users (
    id uuid primary key default gen_random_uuid(),
    phone text not null unique,
    name text,
    whatsapp_opted_in boolean not null default false,
    terms_accepted_at timestamptz,
    privacy_accepted_at timestamptz,
    created_at timestamptz not null default now()
);

alter table users add column if not exists name text;
alter table users add column if not exists whatsapp_opted_in boolean not null default false;
alter table users add column if not exists terms_accepted_at timestamptz;
alter table users add column if not exists privacy_accepted_at timestamptz;

create table if not exists broker_accounts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    broker text not null,
    broker_user_id text,
    access_token_ciphertext text,
    public_token text,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (user_id, broker)
);

create table if not exists holdings_snapshots (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    broker_account_id uuid references broker_accounts(id) on delete set null,
    raw_holdings jsonb not null default '[]'::jsonb,
    summary jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists chat_messages (
    id uuid primary key default gen_random_uuid(),
    thread_id text not null,
    user_id uuid not null references users(id) on delete cascade,
    role text not null check (role in ('user', 'assistant', 'system')),
    content text not null,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists chat_messages_thread_created_idx
    on chat_messages (thread_id, created_at desc);

create table if not exists chat_summaries (
    thread_id text primary key,
    user_id uuid not null references users(id) on delete cascade,
    summary text not null,
    updated_at timestamptz not null default now()
);

create table if not exists pending_actions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    thread_id text not null,
    action_type text not null,
    payload jsonb not null default '{}'::jsonb,
    status text not null default 'pending' check (status in ('pending', 'confirmed', 'cancelled', 'expired')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (thread_id, action_type)
);

create table if not exists alerts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    broker_account_id uuid references broker_accounts(id) on delete set null,
    symbol text not null,
    exchange text not null default 'NSE',
    condition text not null check (condition in ('above', 'below')),
    target_price numeric not null,
    enabled boolean not null default true,
    last_triggered_price numeric,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists alerts_enabled_idx on alerts (enabled, symbol, exchange);

create table if not exists watchlist_items (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    symbol text not null,
    exchange text not null default 'NSE',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (user_id, symbol, exchange)
);

create index if not exists watchlist_items_user_idx on watchlist_items (user_id, created_at desc);

create table if not exists paper_orders (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    symbol text not null,
    exchange text not null default 'NSE',
    side text not null check (side in ('buy', 'sell')),
    quantity integer not null check (quantity > 0),
    order_type text not null default 'market' check (order_type in ('market', 'limit')),
    limit_price numeric,
    status text not null default 'confirmed_paper',
    confirmation_text text not null,
    created_at timestamptz not null default now()
);

create table if not exists audit_events (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references users(id) on delete set null,
    event_type text not null,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

alter table users enable row level security;
alter table broker_accounts enable row level security;
alter table holdings_snapshots enable row level security;
alter table chat_messages enable row level security;
alter table chat_summaries enable row level security;
alter table pending_actions enable row level security;
alter table alerts enable row level security;
alter table watchlist_items enable row level security;
alter table paper_orders enable row level security;
alter table audit_events enable row level security;
