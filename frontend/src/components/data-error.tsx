import { LedgerErrorPanel } from "@/components/error-panel";
import { PageHeader } from "@/components/page-header";
import type { LedgerApiError } from "@/lib/api/client";

export function DataError({
  title,
  description,
  error,
}: {
  title: string;
  description: string;
  error: LedgerApiError;
}) {
  return (
    <>
      <PageHeader title={title} description={description} />
      <LedgerErrorPanel error={error} label="The service did not return this read" />
    </>
  );
}
