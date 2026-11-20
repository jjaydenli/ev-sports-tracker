// The local board's Shut down: ends any page-started run, then both servers.
import { guardedPost } from "@/lib/local-proxy";

export function POST(request: Request): Promise<Response> {
  return guardedPost(request, "/api/local/shutdown");
}
