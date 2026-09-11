import { loadData } from "@/lib/api/server";

/**
 * Proxies `GET /v1/export` so the browser downloads the projection without ever
 * seeing the bearer token. The response is derived, read-only state.
 */
export async function GET(request: Request): Promise<Response> {
  const batchId = new URL(request.url).searchParams.get("batch_id") ?? undefined;
  const result = await loadData("exportData", {
    query: batchId ? { batch_id: batchId } : {},
  });

  if (!result.ok) {
    return new Response(
      JSON.stringify({ error: { code: result.error.code, message: result.error.message } }),
      {
        status: 502,
        headers: { "content-type": "application/json" },
      },
    );
  }

  const suffix = batchId ? `-${batchId}` : "";
  return new Response(JSON.stringify(result.data, null, 2), {
    headers: {
      "content-type": "application/json",
      "content-disposition": `attachment; filename="ledger-export${suffix}.json"`,
    },
  });
}
