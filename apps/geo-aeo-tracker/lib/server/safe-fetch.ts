import dns from "node:dns/promises";
import { isIP } from "node:net";

const MAX_REDIRECTS = 3;
const DEFAULT_MAX_BYTES = 2 * 1024 * 1024;
const DEFAULT_TIMEOUT_MS = 10_000;

function isPrivateIpv4(address: string): boolean {
  const parts = address.split(".").map((part) => Number(part));
  if (parts.length !== 4 || parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) {
    return true;
  }
  const [a, b] = parts;
  return (
    a === 10 ||
    a === 127 ||
    (a === 169 && b === 254) ||
    (a === 172 && b >= 16 && b <= 31) ||
    (a === 192 && b === 168) ||
    (a === 100 && b >= 64 && b <= 127) ||
    a === 0 ||
    a >= 224
  );
}

function isPrivateIpv6(address: string): boolean {
  const lower = address.toLowerCase();
  return (
    lower === "::1" ||
    lower === "::" ||
    lower.startsWith("fc") ||
    lower.startsWith("fd") ||
    lower.startsWith("fe80:") ||
    lower.startsWith("::ffff:127.") ||
    lower.startsWith("::ffff:10.") ||
    lower.startsWith("::ffff:192.168.") ||
    lower.startsWith("::ffff:169.254.")
  );
}

function assertPublicAddress(address: string) {
  const family = isIP(address);
  if (family === 4 && isPrivateIpv4(address)) {
    throw new Error("URL resolves to a non-public address");
  }
  if (family === 6 && isPrivateIpv6(address)) {
    throw new Error("URL resolves to a non-public address");
  }
  if (family === 0) {
    throw new Error("URL resolves to an invalid address");
  }
}

export async function assertPublicHttpUrl(raw: string): Promise<URL> {
  const parsed = new URL(raw);
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error("Only HTTP(S) URLs are allowed");
  }
  const addresses = await dns.lookup(parsed.hostname, { all: true, verbatim: true });
  if (addresses.length === 0) {
    throw new Error("URL host did not resolve");
  }
  for (const { address } of addresses) {
    assertPublicAddress(address);
  }
  return parsed;
}

export async function safeFetchText(
  raw: string,
  options: { maxBytes?: number; timeoutMs?: number; redirects?: number } = {},
): Promise<{ ok: boolean; text: string; status: number; url: string }> {
  let current = raw;
  const maxBytes = options.maxBytes ?? DEFAULT_MAX_BYTES;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const redirects = options.redirects ?? MAX_REDIRECTS;

  for (let i = 0; i <= redirects; i++) {
    const parsed = await assertPublicHttpUrl(current);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(parsed.toString(), {
        headers: { "User-Agent": "GEO-AEO-Tracker/1.0" },
        cache: "no-store",
        redirect: "manual",
        signal: controller.signal,
      });

      if (res.status >= 300 && res.status < 400) {
        const location = res.headers.get("location");
        if (!location) {
          return { ok: false, text: "", status: res.status, url: parsed.toString() };
        }
        current = new URL(location, parsed).toString();
        continue;
      }

      if (!res.ok || !res.body) {
        return { ok: res.ok, text: "", status: res.status, url: parsed.toString() };
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let total = 0;
      let text = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        total += value.byteLength;
        if (total > maxBytes) {
          throw new Error(`Response too large: >${maxBytes} bytes`);
        }
        text += decoder.decode(value, { stream: true });
      }
      text += decoder.decode();
      return { ok: true, text, status: res.status, url: parsed.toString() };
    } finally {
      clearTimeout(timer);
    }
  }

  throw new Error("Too many redirects");
}
