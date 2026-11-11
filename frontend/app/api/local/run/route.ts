// The local board's run trigger.
// Proxies GET|POST /api/local/run to the local board API server-side, so the browser needs
// no CORS and no NEXT_PUBLIC_ variable. Only the local API (backend web/local_board.py)
// serves this route; the cloud API answers 404.

async function proxy(method: "GET" | "POST"): Promise<Response> {
  const apiUrl = process.env.BOARD_API_URL;
  if (!apiUrl) {
    return Response.json({ detail: "BOARD_API_URL is not set" }, { status: 500 });
  }
  try {
    const upstream = await fetch(`${apiUrl.replace(/\/+$/, "")}/api/local/run`, {
      method,
      cache: "no-store",
    });
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return Response.json({ detail: "local board API unreachable" }, { status: 502 });
  }
}

export function GET(): Promise<Response> {
  return proxy("GET");
}

export function POST(): Promise<Response> {
  return proxy("POST");
}
