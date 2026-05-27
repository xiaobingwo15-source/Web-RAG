"""Apply dynamic settings and Shared Knowledge Base migrations to Supabase."""

print("=" * 60)
print("SUPABASE SQL MIGRATION INSTRUCTIONS")
print("=" * 60)
print("To fully enable Dynamic Admin API Settings and Shared Knowledge Base,")
print("you must execute the following SQL in your Supabase SQL Editor.")
print("")
print("URL to open: https://supabase.com/dashboard/project/gfqcgjkentiduplkvacp/sql/new")
print("")
print("------- COPY ALL SQL BELOW AND CLICK RUN -------")
print()

sql_settings = """-- ===================================================
-- 1. SYSTEM SETTINGS TABLE
-- ===================================================
CREATE TABLE IF NOT EXISTS public.system_settings (
    key text PRIMARY KEY,
    value text NOT NULL,
    description text,
    updated_at timestamptz DEFAULT now()
);

ALTER TABLE public.system_settings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Admin manage system_settings" ON public.system_settings;
CREATE POLICY "Admin manage system_settings"
    ON public.system_settings
    FOR ALL
    USING (
        auth.uid() IS NOT NULL 
        AND (
            (SELECT role FROM public.profiles WHERE id = auth.uid()) = 'admin'
            OR (auth.jwt() ->> 'email') = 'admin@example.com'
        )
    )
    WITH CHECK (
        auth.uid() IS NOT NULL 
        AND (
            (SELECT role FROM public.profiles WHERE id = auth.uid()) = 'admin'
            OR (auth.jwt() ->> 'email') = 'admin@example.com'
        )
    );

DROP POLICY IF EXISTS "Authenticated users read system_settings" ON public.system_settings;
CREATE POLICY "Authenticated users read system_settings"
    ON public.system_settings
    FOR SELECT
    USING (auth.uid() IS NOT NULL);

-- ===================================================
-- 2. SHARED KNOWLEDGE BASE RLS POLICIES
-- ===================================================

-- 2.1 Documents Policies
DROP POLICY IF EXISTS "Users manage own documents" ON public.documents;
DROP POLICY IF EXISTS "Select documents policy" ON public.documents;
DROP POLICY IF EXISTS "Modify own documents policy" ON public.documents;

CREATE POLICY "Select documents policy" ON public.documents FOR SELECT
    USING (
        auth.uid() = user_id
        OR (SELECT role FROM public.profiles WHERE id = user_id) = 'admin'
        OR (SELECT role FROM public.profiles WHERE id = auth.uid()) = 'admin'
    );

CREATE POLICY "Modify own documents policy" ON public.documents FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- 2.2 Document Chunks Policies
DROP POLICY IF EXISTS "Users can read own chunks" ON public.document_chunks;
DROP POLICY IF EXISTS "Users can insert own chunks" ON public.document_chunks;
DROP POLICY IF EXISTS "Users can delete own chunks" ON public.document_chunks;
DROP POLICY IF EXISTS "Select chunks policy" ON public.document_chunks;
DROP POLICY IF EXISTS "Insert chunks policy" ON public.document_chunks;
DROP POLICY IF EXISTS "Delete chunks policy" ON public.document_chunks;

CREATE POLICY "Select chunks policy" ON public.document_chunks FOR SELECT
    USING (
        auth.uid() = user_id
        OR (SELECT role FROM public.profiles WHERE id = user_id) = 'admin'
        OR (SELECT role FROM public.profiles WHERE id = auth.uid()) = 'admin'
    );

CREATE POLICY "Insert chunks policy" ON public.document_chunks FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Delete chunks policy" ON public.document_chunks FOR DELETE
    USING (
        auth.uid() = user_id 
        OR (SELECT role FROM public.profiles WHERE id = auth.uid()) = 'admin'
    );

-- ===================================================
-- 3. FIX: PROFILES TABLE READABLE BY ALL AUTH USERS
-- ===================================================
-- Without this, the subqueries in documents/chunks RLS policies fail
-- because a client user cannot read the admin's profile row to check
-- if (SELECT role FROM profiles WHERE id = user_id) = 'admin'.
-- The subquery returns NULL, and the client sees zero shared documents.

CREATE POLICY "Authenticated users can read profiles"
    ON public.profiles FOR SELECT
    USING (auth.uid() IS NOT NULL);
"""

print(sql_settings)
print()
print("------- END OF SQL -------")
print("=" * 60)
print("After running this SQL, the system settings table and")
print("Shared Knowledge Base policies will be active!")
print("=" * 60)
