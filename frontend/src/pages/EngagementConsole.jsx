import { useContent, usePublishContent, useBlueskyAnalytics } from '../hooks/useApi'

const PLATFORM_ICON = {
  twitter:   '𝕏',
  instagram: '📸',
  tiktok:    '♪',
  youtube:   '▶',
  linkedin:  'in',
  facebook:  'f',
  bluesky:   '☁',
}

export default function EngagementConsole() {
  const { data: content, isLoading } = useContent({ page_size: 20 })
  const { data: bluesky }            = useBlueskyAnalytics()
  const publish = usePublishContent()

  const posts = content?.items ?? []

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Engagement Console</h1>
        <p className="text-gray-400 text-sm mt-0.5">Content performance and Bluesky publishing</p>
      </div>

      {/* Bluesky stats */}
      {bluesky && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: 'Published',   value: bluesky.total_posts   ?? 0 },
            { label: 'Likes',       value: bluesky.total_likes   ?? 0 },
            { label: 'Reposts',     value: bluesky.total_reposts ?? 0 },
            { label: 'Replies',     value: bluesky.total_replies ?? 0 },
          ].map(({ label, value }) => (
            <div key={label} className="card text-center">
              <p className="text-2xl font-bold text-brand-300">{value}</p>
              <p className="text-gray-400 text-xs mt-1">{label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Content list */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4">Generated Content</h2>
        {isLoading ? (
          <p className="text-gray-500 text-sm">Loading…</p>
        ) : posts.length === 0 ? (
          <p className="text-gray-500 text-sm">No content generated yet. Run a campaign first.</p>
        ) : (
          <div className="space-y-3">
            {posts.map((post) => (
              <div key={post.id} className="border border-gray-800 rounded-lg p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-base">{PLATFORM_ICON[post.platform] ?? '?'}</span>
                      <span className="text-xs text-gray-400 capitalize">{post.platform}</span>
                      <span className={`badge-${post.status === 'published' ? 'green' : post.status === 'approved' ? 'blue' : 'gray'} text-[10px]`}>
                        {post.status}
                      </span>
                    </div>
                    <p className="text-gray-200 text-sm line-clamp-2">{post.content_text ?? post.caption ?? post.tweet_text ?? '(no text)'}</p>
                    {post.bluesky_uri && (
                      <a
                        href={`https://bsky.app`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-400 text-xs mt-1 hover:underline inline-block"
                      >
                        View on Bluesky →
                      </a>
                    )}
                  </div>
                  <div className="flex flex-col gap-2 shrink-0">
                    {post.platform === 'bluesky' && post.status !== 'published' && (
                      <button
                        className="btn-primary text-xs py-1 px-3"
                        disabled={publish.isPending}
                        onClick={() => publish.mutate(post.id)}
                      >
                        Publish
                      </button>
                    )}
                    <div className="text-right">
                      <p className="text-gray-600 text-xs">{post.likes ?? 0} ♥</p>
                      <p className="text-gray-600 text-xs">{post.reposts ?? 0} ↺</p>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
