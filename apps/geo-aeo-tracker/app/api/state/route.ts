import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { isCloudStorageConfigured } from "@/lib/server/supabase";
import { kvGet, kvSet, kvDelete } from "@/lib/server/kv-store";
import { requireInternalApiToken, checkRateLimit } from "@/lib/server/api-guard";

// supabase-js requires Node APIs — stay on the Node runtime.
export const runtime = "nodejs";
// State mutations should always read the latest row; opt out of caching.
export const dynamic = "force-dynamic";

const keySchema = z.string().min(1).max(512);
const putBodySchema = z.object({
  key: keySchema,
  value: z.unknown(),
});

function notConfigured() {
  return NextResponse.json(
    { error: "Cloud storage is not configured on this deployment." },
    { status: 501 },
  );
}

export async function GET(req: NextRequest) {
  if (!isCloudStorageConfigured()) return notConfigured();
  const guarded = requireInternalApiToken(req, "GEO_AEO_TRACKER_STATE_TOKEN") ?? checkRateLimit(req, "state", 60);
  if (guarded) return guarded;

  const key = req.nextUrl.searchParams.get("key");
  const parsed = keySchema.safeParse(key);
  if (!parsed.success) {
    return NextResponse.json({ error: "Missing or invalid `key` param." }, { status: 400 });
  }

  const res = await kvGet(parsed.data);
  if (!res.ok) return NextResponse.json({ error: res.error }, { status: 500 });
  return NextResponse.json({ key: parsed.data, value: res.value });
}

export async function PUT(req: NextRequest) {
  if (!isCloudStorageConfigured()) return notConfigured();
  const guarded = requireInternalApiToken(req, "GEO_AEO_TRACKER_STATE_TOKEN") ?? checkRateLimit(req, "state", 30);
  if (guarded) return guarded;

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const parsed = putBodySchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid body: expected {key, value}." }, { status: 400 });
  }

  const res = await kvSet(parsed.data.key, parsed.data.value);
  if (!res.ok) return NextResponse.json({ error: res.error }, { status: 500 });
  return NextResponse.json({ ok: true });
}

export async function DELETE(req: NextRequest) {
  if (!isCloudStorageConfigured()) return notConfigured();
  const guarded = requireInternalApiToken(req, "GEO_AEO_TRACKER_STATE_TOKEN") ?? checkRateLimit(req, "state", 30);
  if (guarded) return guarded;

  const key = req.nextUrl.searchParams.get("key");
  const parsed = keySchema.safeParse(key);
  if (!parsed.success) {
    return NextResponse.json({ error: "Missing or invalid `key` param." }, { status: 400 });
  }

  const res = await kvDelete(parsed.data);
  if (!res.ok) return NextResponse.json({ error: res.error }, { status: 500 });
  return NextResponse.json({ ok: true });
}
