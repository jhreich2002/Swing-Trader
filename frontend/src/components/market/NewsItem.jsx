function timeAgo(unixTs) {
  if (!unixTs) return ""
  const diff = Math.floor((Date.now() / 1000 - unixTs) / 3600)
  if (diff < 1) return "< 1h ago"
  if (diff < 24) return `${diff}h ago`
  return `${Math.floor(diff / 24)}d ago`
}

export default function NewsItem({ article }) {
  const { headline, source, url, datetime, summary } = article
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="block bg-card border border-border rounded-lg p-4 hover:border-accent/50 transition-colors group"
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-sm font-medium text-gray-200 group-hover:text-white leading-snug line-clamp-2">
          {headline}
        </h3>
      </div>
      {summary && (
        <p className="text-xs text-gray-500 mt-1.5 line-clamp-2">{summary}</p>
      )}
      <div className="flex items-center gap-2 mt-2 text-xs text-gray-600">
        <span>{source}</span>
        <span>·</span>
        <span>{timeAgo(datetime)}</span>
      </div>
    </a>
  )
}
