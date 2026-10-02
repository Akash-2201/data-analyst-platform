/**
 * Supabase client for frontend authentication.
 *
 * Uses only the public anon key — the service role key stays backend-only.
 * The Supabase client automatically manages session tokens in localStorage.
 */

import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL = "https://mgaehyiijhvfsncbommx.supabase.co";
const SUPABASE_ANON_KEY =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1nYWVoeWlpamh2ZnNuY2JvbW14Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTA0Mzg4MjEsImV4cCI6MjEwNjAxNDgyMX0.NLZzoHKu8mYQa66gKCDOBDTfX19H5xm1tV2_TaTbSx8";

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
