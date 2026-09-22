import { type NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

function apiOrigin(): string {
  return (
    process.env.API_REWRITE_TARGET ??
    process.env.NEXT_PUBLIC_API_BASE_URL ??
    "http://127.0.0.1:8000"
  ).replace(/\/$/, "");
}

/**
 * Stream chat SSE through a Node route. Vercel platform rewrites buffer the
 * FastAPI stream, so the UI stays on "Understanding your question".
 */
export async function POST(request: NextRequest) {
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (lower === "host" || lower === "connection" || lower === "content-length") {
      return;
    }
    headers.set(key, value);
  });

  const upstream = await fetch(`${apiOrigin()}/api/v1/chat/ask`, {
    method: "POST",
    headers,
    body: request.body,
    cache: "no-store",
    // Required so Node can stream the request body to FastAPI.
    // @ts-expect-error undici duplex is not on the DOM RequestInit type
    duplex: "half",
  });

  const out = new Headers();
  const pass = ["content-type", "cache-control", "x-request-id", "x-accel-buffering"];
  for (const name of pass) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  out.set("Content-Type", "text/event-stream; charset=utf-8");
  out.set("Cache-Control", "no-cache, no-transform");
  out.set("X-Accel-Buffering", "no");

  return new Response(upstream.body, {
    status: upstream.status,
    headers: out,
  });
}
