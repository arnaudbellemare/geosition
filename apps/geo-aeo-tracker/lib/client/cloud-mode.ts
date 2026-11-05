"use client";

/**
 * Cloud storage mode detection + user-facing override.
 *
 * Cloud is available when the app was built/deployed with Supabase env vars.
 * The build step exposes `NEXT_PUBLIC_CLOUD_STORAGE_ENABLED` so the client
 * knows to render the toggle and hit /api/state.
 *
 * Users can still force local-only via a per-browser preference stored in
 * localStorage (key: "sovereign-cloud-sync"). This preserves the
 * local-first / BYOK spirit of the project.
 */

const CLOUD_PREF_KEY = "sovereign-cloud-sync";

export function isCloudAvailable(): boolean {
  // NEXT_PUBLIC_ vars are inlined at build time
  return process.env.NEXT_PUBLIC_CLOUD_STORAGE_ENABLED === "true";
}

export function isCloudEnabledByUser(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const raw = window.localStorage.getItem(CLOUD_PREF_KEY);
    // Default to "on" when cloud is available and no preference set yet.
    if (raw === null) return true;
    return raw === "true";
  } catch {
    return true;
  }
}

export function setCloudEnabledByUser(enabled: boolean): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(CLOUD_PREF_KEY, enabled ? "true" : "false");
  } catch {
    /* ignore quota errors */
  }
}

/** True when cloud is configured AND the user hasn't disabled it. */
export function isCloudActive(): boolean {
  return isCloudAvailable() && isCloudEnabledByUser();
}
