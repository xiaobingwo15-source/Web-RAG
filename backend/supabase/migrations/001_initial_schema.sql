-- Threads table
create table if not exists public.threads (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    title text not null default 'New Chat',
    created_at timestamptz not null default now()
);

-- Messages table
create table if not exists public.messages (
    id uuid primary key default gen_random_uuid(),
    thread_id uuid not null references public.threads(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    role text not null check (role in ('user', 'assistant')),
    content text not null,
    created_at timestamptz not null default now()
);

-- Enable RLS
alter table public.threads enable row level security;
alter table public.messages enable row level security;

-- RLS policies for threads
create policy "Users can view own threads"
    on public.threads for select
    using (user_id = auth.uid());

create policy "Users can insert own threads"
    on public.threads for insert
    with check (user_id = auth.uid());

create policy "Users can update own threads"
    on public.threads for update
    using (user_id = auth.uid());

create policy "Users can delete own threads"
    on public.threads for delete
    using (user_id = auth.uid());

-- RLS policies for messages
create policy "Users can view own messages"
    on public.messages for select
    using (user_id = auth.uid());

create policy "Users can insert own messages"
    on public.messages for insert
    with check (user_id = auth.uid());

create policy "Users can update own messages"
    on public.messages for update
    using (user_id = auth.uid());

create policy "Users can delete own messages"
    on public.messages for delete
    using (user_id = auth.uid());

-- Indexes
create index if not exists idx_threads_user_id on public.threads(user_id);
create index if not exists idx_messages_thread_id on public.messages(thread_id);
create index if not exists idx_messages_user_id on public.messages(user_id);
