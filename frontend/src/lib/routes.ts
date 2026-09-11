import type { Route } from "next";

/**
 * Type a dynamically constructed dashboard route. Static links keep Next's
 * typed-route checking; links that carry query parameters (for example
 * `/reconciliation?batch_id=…`) must pass through here.
 */
export function route(pathWithQuery: string): Route {
  return pathWithQuery as Route;
}
