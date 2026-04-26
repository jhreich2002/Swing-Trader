export default function SynthesisCard({ synthesis, themes, loading }) {
  if (loading) {
    return (
      <div className="bg-card border border-border rounded-xl p-5 animate-pulse">
        <div className="h-4 bg-border rounded w-1/3 mb-4" />
        <div className="space-y-2">
          <div className="h-3 bg-border rounded w-full" />
          <div className="h-3 bg-border rounded w-11/12" />
          <div className="h-3 bg-border rounded w-10/12" />
        </div>
      </div>
    )
  }

  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest mb-3">
        AI Market Synthesis
      </h2>
      {synthesis ? (
        <>
          <div className="text-gray-200 text-sm leading-relaxed whitespace-pre-line mb-4">
            {synthesis}
          </div>
          {themes && themes.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-widest mb-2">Key Themes</p>
              <ul className="space-y-1">
                {themes.map((t, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-300">
                    <span className="text-accent mt-0.5">›</span>
                    {t}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      ) : (
        <p className="text-gray-500 text-sm">Synthesis unavailable.</p>
      )}
    </div>
  )
}
