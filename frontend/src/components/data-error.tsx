import { ContractCalls } from "@/components/contract-calls";
import { LedgerErrorPanel } from "@/components/error-panel";
import { PageHeader } from "@/components/page-header";
import type { GeneratedOperationId } from "@/lib/api/operations.generated";
import type { LedgerApiError } from "@/lib/api/client";

/**
 * A read that failed. The contract error code, HTTP status, and correlation id
 * are rendered verbatim instead of a generic failure, and the page still states
 * the operations it depends on.
 */
export function DataError({
  title,
  description,
  error,
  operations,
}: {
  title: string;
  description: string;
  error: LedgerApiError;
  operations: readonly GeneratedOperationId[];
}) {
  return (
    <>
      <PageHeader title={title} description={description} />
      <LedgerErrorPanel error={error} label="The service did not return this read" />
      <ContractCalls operations={operations} />
    </>
  );
}
