import { NextRequest, NextResponse } from "next/server";

const WINDOW_MS = 60_000;
const buckets = new Map<string, { count: number; resetAt: number }>();

function tokenFromAuthHeader(req: NextRequest): string {
  const auth = req.headers.get("authorization") ?? "";
  return auth.replace(/^Bearer\s+/i, "").trim();
}

function clientKey(req: NextRequest): string {
  return (
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    req.headers.get("x-real-ip") ||
    "unknown"
  );
}

export function requireInternalApiToken(req: NextRequest, envName = "GEO_AEO_TRACKER_API_TOKEN") {
  const expected = process.env[envName]?.trim();
  const provided = tokenFromAuthHeader(req);
  if (!expected && process.env.NODE_ENV !== "production") {
    return null;
  }
  if (!expected || !provided || provided !== expected) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  return null;
}

export function checkRateLimit(req: NextRequest, key: string, limit = 30) {
  const now = Date.now();
  const bucketKey = `${key}:${clientKey(req)}`;
  const current = buckets.get(bucketKey);
  if (!current || current.resetAt <= now) {
    buckets.set(bucketKey, { count: 1, resetAt: now + WINDOW_MS });
    return null;
  }
  if (current.count >= limit) {
    return NextResponse.json({ error: "Too many requests" }, { status: 429 });
  }
  current.count += 1;
  return null;
}

export function guardProviderRoute(req: NextRequest, key: string, limit = 20) {
  return requireInternalApiToken(req) ?? checkRateLimit(req, key, limit);
}
