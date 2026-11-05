import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { guardProviderRoute } from "@/lib/server/api-guard";
import { analyzeGrounding } from "@/lib/server/gemini-grounding";

const requestSchema = z.object({
  keyword: z.string().min(1),
  targetUrl: z.string().url(),
});

export async function POST(req: NextRequest) {
  const guarded = guardProviderRoute(req, "grounding", 20);
  if (guarded) return guarded;

  try {
    const body = await req.json();
    const parsed = requestSchema.parse(body);
    const result = await analyzeGrounding(parsed.keyword, parsed.targetUrl);
    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
