// Read at BUILD time: Next inlines NEXT_PUBLIC_* values into the browser bundle,
// so set them in Vercel (or .env.local) before `next build`.
export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
// The anon / publishable key. Safe for the browser: row-level security protects the data.
// The service-role key must NEVER appear here.
export const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

export const KISAN_CALL_CENTRE = "1800-180-1551";
