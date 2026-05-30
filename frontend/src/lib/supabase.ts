import { createClient } from '@supabase/supabase-js'

const requireEnv = (value: string | undefined, name: string) => {
  if (!value) {
    throw new Error(
      `Missing ${name}. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in Vercel, or provide SUPABASE_URL and SUPABASE_ANON_KEY at build time.`
    )
  }
  return value
}

const supabaseUrl = requireEnv(import.meta.env.VITE_SUPABASE_URL, 'Supabase URL')
const supabaseAnonKey = requireEnv(import.meta.env.VITE_SUPABASE_ANON_KEY, 'Supabase anon key')

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
