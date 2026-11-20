// The local board's Stop: ends a page-started auto-refresh.
import { guardedPost } from "@/lib/local-proxy";

export function POST(request: Request): Promise<Response> {
  return guardedPost(request, "/api/local/stop");
}
