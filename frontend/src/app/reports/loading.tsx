function Skel({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-surface-sunken ${className}`} />;
}

export default function ReportsLoading() {
  return (
    <>
      <div className="mb-4 border-b border-line pb-3">
        <Skel className="h-5 w-20" />
        <Skel className="mt-1 h-4 w-96 max-w-full" />
      </div>

      <div className="mb-4 flex flex-wrap items-end gap-2">
        <div>
          <Skel className="h-3 w-16" />
          <Skel className="mt-1 h-7 w-72 max-w-full rounded-control" />
        </div>
        <Skel className="h-7 w-20 rounded-control" />
      </div>

      <dl className="mb-4 grid grid-cols-1 divide-y divide-line overflow-hidden rounded-panel border border-line bg-surface sm:grid-cols-3 sm:divide-y-0 sm:divide-x lg:grid-cols-6">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="px-4 py-3">
            <Skel className="h-3 w-20" />
            <Skel className="mt-1 h-6 w-14" />
            <Skel className="mt-1 h-3 w-16" />
          </div>
        ))}
      </dl>

      <Skel className="mb-2 h-3 w-48" />
      <div className="mb-6 overflow-x-auto rounded-panel border border-line bg-surface">
        <table className="w-full border-collapse">
          <thead className="border-b border-line bg-surface-muted">
            <tr>
              {[0, 1, 2, 3].map((i) => (
                <th key={i} className="px-3 py-2 text-left">
                  <Skel className="h-3 w-16" />
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {[0, 1, 2, 3, 4, 5, 6].map((i) => (
              <tr key={i}>
                <td className="px-3 py-2"><Skel className="h-5 w-20 rounded-full" /></td>
                <td className="px-3 py-2 text-right"><Skel className="ml-auto h-4 w-12" /></td>
                <td className="px-3 py-2 text-right"><Skel className="ml-auto h-4 w-12" /></td>
                <td className="px-3 py-2"><Skel className="h-4 w-32" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <section className="rounded-panel border border-line bg-surface">
        <div className="border-b border-line px-4 py-2">
          <Skel className="h-3 w-32" />
        </div>
        <div className="space-y-3 px-4 py-3">
          <Skel className="h-4 w-full max-w-lg" />
          <Skel className="h-4 w-80 max-w-full" />
          <div className="flex items-center gap-3">
            <Skel className="h-7 w-24 rounded-control" />
            <Skel className="h-3 w-40" />
          </div>
        </div>
      </section>
    </>
  );
}
