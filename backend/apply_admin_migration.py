"""Apply admin RLS and User Profiles migrations to Supabase."""

print("=" * 60)
print("SUPABASE SQL MIGRATION INSTRUCTIONS")
print("=" * 60)
print("To fully enable the Admin Portal and Database-Backed Roles,")
print("you must execute the following SQL in your Supabase SQL Editor.")
print("")
print("URL to open: https://supabase.com/dashboard/project/gfqcgjkentiduplkvacp/sql/new")
print("")
print("------- COPY ALL SQL BELOW AND CLICK RUN -------")
print()

sql = """-- ===================================================
-- 1. ADMIN RLS POLICIES (Bypass RLS for admin user)
-- ===================================================

-- Admin can read all threads
drop policy if exists "Admin can view all threads" on public.threads;
create policy "Admin can view all threads"
    on public.threads for select
    using (
        auth.uid() is not null
        and (auth.jwt() ->> 'email') = 'admin@example.com'
    );

-- Admin can read all messages
drop policy if exists "Admin can view all messages" on public.messages;
create policy "Admin can view all messages"
    on public.messages for select
    using (
        auth.uid() is not null
        and (auth.jwt() ->> 'email') = 'admin@example.com'
    );

-- ===================================================
-- 2. USER PROFILES AND DATABASE-BACKED ROLES
-- ===================================================

-- Create profiles table
create table if not exists public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    email text not null,
    role text not null default 'client' check (role in ('admin', 'client')),
    created_at timestamptz not null default now()
);

-- Enable RLS on profiles
alter table public.profiles enable row level security;

-- Create policies for profiles
drop policy if exists "Users can view own profile" on public.profiles;
create policy "Users can view own profile"
    on public.profiles for select
    using (id = auth.uid());

drop policy if exists "Users can update own profile" on public.profiles;
create policy "Users can update own profile"
    on public.profiles for update
    using (id = auth.uid());

drop policy if exists "Admin can view all profiles" on public.profiles;
create policy "Admin can view all profiles"
    on public.profiles for select
    using (
        auth.uid() is not null
        and (
            (select role from public.profiles where id = auth.uid()) = 'admin'
            or
            (auth.jwt() ->> 'email') = 'admin@example.com'
        )
    );


-- Create trigger function to sync new auth.users signup
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

-- Populate existing users into public.profiles
insert into public.profiles (id, email, role)
select id, email, case when email = 'admin@example.com' then 'admin' else 'client' end
from auth.users
on conflict (id) do nothing;
"""

print(sql)
print()
print("------- END OF SQL -------")
print("=" * 60)
print("After running this SQL, both test accounts will be fully configured")
print("with database-backed roles, and any future signups will be")
print("automatically assigned the 'client' role in the profiles table!")
print("=" * 60)

