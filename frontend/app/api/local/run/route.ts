// The local board's run state (GET) and Refresh (POST: one ./ev run).
import { guardedPost, proxy } from "@/lib/local-proxy";

export function GET(): Promise<Response> {
  return proxy("GET", "/api/local/run");
}

export function POST(request: Request): Promise<Response> {
  return guardedPost(request, "/api/local/run");
}
