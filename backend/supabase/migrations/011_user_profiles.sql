-- Migration 011: User Profiles and Roles Table
-- Create profiles table, sync with auth.users, and configure roles.

-- 1. Create profiles table
create table if not exists public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    email text not null,
    role text not null default 'client' check (role in ('admin', 'client')),
    created_at timestamptz not null default now()
);

-- 2. Enable RLS
alter table public.profiles enable row level security;

-- 3. Create policies
create policy "Users can view own profile"
    on public.profiles for select
    using (id = auth.uid());

create policy "Admin can view all profiles"
    on public.profiles for select
    using (auth.uid() is not null and public.is_admin());


-- 4. Create trigger to sync new auth.users signup
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, email, role)
  values (
    new.id,
    new.email,
    case
      when new.email = 'admin@example.com' then 'admin'
      else 'client'
    end
  );
  return new;
end;
$$ language plpgsql security definer;

-- Recreate trigger cleanly
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- 5. Populate existing users into public.profiles
insert into public.profiles (id, email, role)
select id, email, case when email = 'admin@example.com' then 'admin' else 'client' end
from auth.users
on conflict (id) do nothing;
