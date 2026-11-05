import { getServerSupabase } from "./supabase";

/**
 * Server-side KV operations backed by Supabase `kv_store` table.
 * Mirrors the contract of lib/client/sovereign-store.ts so clients can
 * swap between local IndexedDB and cloud transparently.
 */

export type KvResult<T> =
  | { ok: true; value: T | null }
  | { ok: false; error: string };

export async function kvGet<T = unknown>(key: string): Promise<KvResult<T>> {
  const supabase = getServerSupabase();
  if (!supabase) return { ok: false, error: "cloud-not-configured" };

  const { data, error } = await supabase
    .from("kv_store")
    .select("value")
    .eq("key", key)
    .maybeSingle();

  if (error) return { ok: false, error: error.message };
  return { ok: true, value: (data?.value ?? null) as T | null };
}

export async function kvSet<T = unknown>(key: string, value: T): Promise<KvResult<null>> {
  const supabase = getServerSupabase();
  if (!supabase) return { ok: false, error: "cloud-not-configured" };

  const { error } = await supabase
    .from("kv_store")
    .upsert({ key, value }, { onConflict: "key" });

  if (error) return { ok: false, error: error.message };
  return { ok: true, value: null };
}

export async function kvDelete(key: string): Promise<KvResult<null>> {
  const supabase = getServerSupabase();
  if (!supabase) return { ok: false, error: "cloud-not-configured" };

  const { error } = await supabase.from("kv_store").delete().eq("key", key);
  if (error) return { ok: false, error: error.message };
  return { ok: true, value: null };
}
