function Skel({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-surface-sunken ${className}`} />;
}

export default function DashboardLoading() {
  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <Skel className="h-5 w-48" />
          <Skel className="h-3 w-72" />
        </div>
        <Skel className="h-8 w-36 rounded-panel" />
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="rounded-panel border border-line bg-surface px-4 py-4">
            <Skel className="h-3 w-24" />
            <Skel className="mt-2 h-7 w-16" />
          </div>
        ))}
      </div>

      <div className="rounded-panel border border-line bg-surface p-4">
        <Skel className="mb-3 h-3 w-56" />
        <Skel className="h-6 w-full rounded-full" />
        <div className="mt-3 flex flex-wrap gap-4">
          {[0, 1, 2, 3].map((i) => (
            <Skel key={i} className="h-3 w-20" />
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {[0, 1].map((i) => (
          <section key={i} className="rounded-panel border border-line bg-surface">
            <div className="flex items-center justify-between border-b border-line px-4 py-2">
              <Skel className="h-3 w-24" />
              <Skel className="h-3 w-14" />
            </div>
            <ul className="divide-y divide-line">
              {[0, 1, 2, 3, 4].map((j) => (
                <li key={j} className="flex items-center justify-between px-4 py-3">
                  <div className="space-y-1.5">
                    <Skel className="h-3 w-40" />
                    <Skel className="h-3 w-28" />
                  </div>
                  <Skel className="h-4 w-10" />
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
