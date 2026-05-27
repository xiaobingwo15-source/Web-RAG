-- Migration 013: Create system_settings table
CREATE TABLE IF NOT EXISTS public.system_settings (
    key text PRIMARY KEY,
    value text NOT NULL,
    description text,
    updated_at timestamptz DEFAULT now()
);

-- Enable RLS
ALTER TABLE public.system_settings ENABLE ROW LEVEL SECURITY;

-- Admin can do all operations
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
