import type { Route } from "next";

/**
 * Type a dynamically constructed dashboard route. Static links keep Next's
 * typed-route checking; links that carry query parameters (for example
 * `/reconciliation?batch_id=…`) must pass through here.
 */
export function route(pathWithQuery: string): Route {
  return pathWithQuery as Route;
}

/**
 * Dynamic route params arrive percent-encoded, so an id that contains a
 * reserved character (LEDGER ids contain ":") reaches the page as
 * "discrepancy%3A…". Decode exactly once before handing the id to the client,
 * which encodes it again for the outbound `/v1` request.
 */
export function decodeRouteParam(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}
