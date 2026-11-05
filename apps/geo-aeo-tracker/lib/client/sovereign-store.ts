"use client";

import { get, set } from "idb-keyval";
import { isCloudActive } from "./cloud-mode";

/**
 * Storage abstraction for the geo-aeo-tracker app.
 *
 * Two modes, chosen per-call:
 * - Local (default): IndexedDB is source of truth, localStorage is a fast-path
 *   cache that may be incomplete (quota limited).
 * - Cloud (when Supabase env is configured AND user hasn't opted out):
 *   The /api/state route (Supabase) is source of truth; IDB is a read cache.
 *
 * The key/value contract is identical in both modes so consumers don't care.
 */

async function cloudGet<T>(key: string): Promise<T | null> {
  const res = await fetch(`/api/state?key=${encodeURIComponent(key)}`, {
    method: "GET",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`cloud GET failed: ${res.status}`);
  const data = (await res.json()) as { value: T | null };
  return data.value;
}

async function cloudPut<T>(key: string, value: T): Promise<void> {
  const res = await fetch(`/api/state`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  });
  if (!res.ok) throw new Error(`cloud PUT failed: ${res.status}`);
}

async function cloudDelete(key: string): Promise<void> {
  const res = await fetch(`/api/state?key=${encodeURIComponent(key)}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 404) {
    throw new Error(`cloud DELETE failed: ${res.status}`);
  }
}

/**
 * Load state.
 *
 * Cloud mode: read from /api/state. On failure, fall back to IDB so the app
 *   keeps working offline / during Supabase free-tier cold-starts.
 * Local mode: IDB first, localStorage second, fallback third.
 */
export async function loadSovereignValue<T>(key: string, fallback: T): Promise<T> {
  if (isCloudActive()) {
    try {
      const cloudValue = await cloudGet<T>(key);
      if (cloudValue !== null && cloudValue !== undefined) {
        // Warm IDB cache so subsequent reads stay snappy
        set(key, cloudValue).catch(() => {});
        return cloudValue;
      }
    } catch (err) {
      // Network / server error — fall through to local cache
      if (typeof console !== "undefined") {
        console.warn("[sovereign-store] cloud load failed, using local cache:", err);
      }
    }
    // Cloud returned no value OR failed — try IDB as cache
    try {
      const cached = await get<T>(key);
      if (cached !== undefined) return cached;
    } catch { /* ignore */ }
    return fallback;
  }

  // Local mode (original behavior)
  try {
    const indexed = await get<T>(key);
    if (indexed !== undefined) return indexed;

    const localRaw = window.localStorage.getItem(key);
    if (localRaw) {
      const parsed = JSON.parse(localRaw) as T;
      await set(key, parsed).catch(() => {});
      return parsed;
    }
  } catch {
    try {
      const localRaw = window.localStorage.getItem(key);
      if (localRaw) return JSON.parse(localRaw) as T;
    } catch { /* give up */ }
  }

  return fallback;
}

/**
 * Save state.
 *
 * Cloud mode: write to /api/state. Also mirror to IDB so we have a local
 *   cache for offline / fast reloads.
 * Local mode: IDB primary, localStorage best-effort cache.
 */
export async function saveSovereignValue<T>(key: string, value: T): Promise<void> {
  await set(key, value);

  try {
    const serialized = JSON.stringify(value);
    window.localStorage.setItem(key, serialized);
  } catch {
    try { window.localStorage.removeItem(key); } catch { /* ignore */ }
  }

  if (isCloudActive()) {
    try {
      await cloudPut(key, value);
    } catch (err) {
      if (typeof console !== "undefined") {
        console.warn("[sovereign-store] cloud save failed, saved locally:", err);
      }
    }
    return;
  }
}

export async function clearSovereignStore(key: string): Promise<void> {
  // Always clear local caches
  try { window.localStorage.removeItem(key); } catch { /* ignore */ }
  const { del } = await import("idb-keyval");
  await del(key).catch(() => {});

  // Also clear cloud copy when active
  if (isCloudActive()) {
    try {
      await cloudDelete(key);
    } catch (err) {
      if (typeof console !== "undefined") {
        console.warn("[sovereign-store] cloud delete failed:", err);
      }
    }
  }
}
