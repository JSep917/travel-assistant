create table if not exists threads (
    thread_id text primary key,
    tenant_id text,
    user_id text not null,
    title text,
    last_message_preview text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    archived_at timestamptz
);

alter table threads
add column if not exists title_source text not null default 'auto';


create table if not exists user_profiles (
    user_id text primary key,
    tenant_id text,
    profile jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now()
);