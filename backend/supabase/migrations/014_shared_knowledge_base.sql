-- Migration 014: Shared Knowledge Base RLS Policies
-- Allow clients to read admin-uploaded documents and chunks.

-- 1. Documents Policies
DROP POLICY IF EXISTS "Users manage own documents" ON public.documents;
DROP POLICY IF EXISTS "Select documents policy" ON public.documents;
DROP POLICY IF EXISTS "Modify own documents policy" ON public.documents;

CREATE POLICY "Select documents policy" ON public.documents FOR SELECT
    USING (
        auth.uid() = user_id -- Own documents
        OR (SELECT role FROM public.profiles WHERE id = user_id) = 'admin' -- Admin-uploaded documents (shared knowledge base)
        OR (SELECT role FROM public.profiles WHERE id = auth.uid()) = 'admin' -- Admins can read all
    );

CREATE POLICY "Modify own documents policy" ON public.documents FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);


-- 2. Document Chunks Policies
DROP POLICY IF EXISTS "Users can read own chunks" ON public.document_chunks;
DROP POLICY IF EXISTS "Users can insert own chunks" ON public.document_chunks;
DROP POLICY IF EXISTS "Users can delete own chunks" ON public.document_chunks;
DROP POLICY IF EXISTS "Select chunks policy" ON public.document_chunks;
DROP POLICY IF EXISTS "Insert chunks policy" ON public.document_chunks;
DROP POLICY IF EXISTS "Delete chunks policy" ON public.document_chunks;

CREATE POLICY "Select chunks policy" ON public.document_chunks FOR SELECT
    USING (
        auth.uid() = user_id -- Own chunks
        OR (SELECT role FROM public.profiles WHERE id = user_id) = 'admin' -- Admin-uploaded chunks (shared knowledge base)
        OR (SELECT role FROM public.profiles WHERE id = auth.uid()) = 'admin' -- Admins can read all
    );

CREATE POLICY "Insert chunks policy" ON public.document_chunks FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Delete chunks policy" ON public.document_chunks FOR DELETE
    USING (
        auth.uid() = user_id 
        OR (SELECT role FROM public.profiles WHERE id = auth.uid()) = 'admin'
    );
