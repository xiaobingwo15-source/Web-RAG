-- Migration 010: Admin RLS policies
-- Allow admin role to read ALL threads and messages (for admin dashboard)
-- Uses public.is_admin() SECURITY DEFINER function to avoid infinite recursion

-- Admin can read all threads
create policy "Admin can view all threads"
    on public.threads for select
    using (auth.uid() is not null and public.is_admin());

-- Admin can read all messages
create policy "Admin can view all messages"
    on public.messages for select
    using (auth.uid() is not null and public.is_admin());

