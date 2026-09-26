function Skel({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-surface-sunken ${className}`} />;
}

export default function ExceptionDetailLoading() {
  return (
    <>
      <div className="mb-4 border-b border-line pb-3">
        <Skel className="h-5 w-24" />
        <Skel className="mt-1 h-4 w-64" />
      </div>

      <Skel className="mb-1 h-3 w-32" />

      <div className="mb-6 rounded-panel border border-line bg-surface">
        <div className="border-b border-line px-4 py-2">
          <Skel className="h-3 w-32" />
        </div>
        <div className="space-y-3 p-4">
          <div>
            <Skel className="h-3 w-24" />
            <Skel className="mt-1 h-7 w-48 rounded-control" />
          </div>
          <div>
            <Skel className="h-3 w-24" />
            <Skel className="mt-1 h-16 w-full rounded-control" />
          </div>
          <div>
            <Skel className="h-3 w-24" />
            <Skel className="mt-1 h-12 w-full rounded-control" />
          </div>
          <Skel className="h-7 w-36 rounded-control" />
        </div>
      </div>

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
        {[0, 1].map((i) => (
          <section key={i} className="rounded-panel border border-line bg-surface">
            <div className="border-b border-line px-4 py-2">
              <Skel className="h-3 w-24" />
            </div>
            <dl className="divide-y divide-line">
              {[0, 1, 2, 3].map((j) => (
                <div key={j} className="px-4 py-3">
                  <Skel className="h-3 w-20" />
                  <Skel className="mt-1 h-4 w-36" />
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>

      <section className="mt-4 rounded-panel border border-line bg-surface">
        <div className="border-b border-line px-4 py-2">
          <Skel className="h-3 w-20" />
        </div>
        <ol className="divide-y divide-line">
          {[0, 1, 2].map((i) => (
            <li key={i} className="flex items-start gap-4 px-4 py-3">
              <Skel className="h-5 w-5 rounded-full" />
              <div className="flex-1 space-y-1.5">
                <Skel className="h-3 w-48" />
                <Skel className="h-3 w-32" />
              </div>
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}
