// The local board's Auto-refresh: starts ./loop.
import { guardedPost } from "@/lib/local-proxy";

export function POST(request: Request): Promise<Response> {
  return guardedPost(request, "/api/local/loop");
}
