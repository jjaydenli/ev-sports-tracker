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

/**
 * True when the request comes from this page: the `Origin` host matches the host the
 * browser asked for, either as sent (`Host`) or as a port forwarder reports it
 * (`x-forwarded-host`). Keeps another website open in the browser from starting runs.
 */
function sameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  let originHost: string;
  try {
    originHost = new URL(origin).host;
  } catch {
    return false;
  }
  const forwarded = request.headers.get("x-forwarded-host")?.split(",")[0]?.trim();
  return [forwarded, request.headers.get("host")].includes(originHost);
}

export function GET(): Promise<Response> {
  return proxy("GET");
}

export async function POST(request: Request): Promise<Response> {
  if (!sameOrigin(request)) {
    return Response.json({ detail: "cross-site request refused" }, { status: 403 });
  }
  return proxy("POST");
}
