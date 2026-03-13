import { useAgentStats } from '../hooks/useApi'

const MENTOR_TIPS = [
  { tip: 'Lead with a strong hook in the first 3 words of every post.', agent: 'Mentor' },
  { tip: 'Hashtags perform 30% better when placed in the first comment, not the caption.', agent: 'Trend' },
  { tip: 'Consistency in brand voice builds trust — avoid mixing formal and casual in the same week.', agent: 'Brand' },
  { tip: 'Risk scores above 0.75 are auto-rejected by the CMO. Frame edgy ideas carefully.', agent: 'Risk' },
  { tip: 'Engagement peaks Tuesday–Thursday 9–11 AM local time for B2B, weekends for B2C.', agent: 'Engagement' },
  { tip: 'Bluesky posts under 240 characters receive 18% more engagement than longer ones.', agent: 'Mentor' },
]

export default function MentorPortal() {
  const { data: stats } = useAgentStats({ window: 'week' })
  const mentorStats = stats?.mentor ?? {}

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Mentor Portal</h1>
        <p className="text-gray-400 text-sm mt-0.5">Strategic advice distilled from the AI Council's debates</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <div className="card text-center">
          <p className="text-3xl font-bold text-cyan-400">{mentorStats.total_calls ?? '—'}</p>
          <p className="text-gray-400 text-xs mt-1">Mentor Reviews (week)</p>
        </div>
        <div className="card text-center">
          <p className="text-3xl font-bold text-emerald-400">{mentorStats.approved ?? '—'}</p>
          <p className="text-gray-400 text-xs mt-1">Content Endorsed</p>
        </div>
        <div className="card text-center">
          <p className="text-3xl font-bold text-brand-300">
            {mentorStats.avg_confidence !== undefined
              ? `${(mentorStats.avg_confidence * 100).toFixed(0)}%`
              : '—'}
          </p>
          <p className="text-gray-400 text-xs mt-1">Avg Mentor Confidence</p>
        </div>
      </div>

      {/* Tips */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4">Strategic Insights</h2>
        <div className="space-y-3">
          {MENTOR_TIPS.map(({ tip, agent }, i) => (
            <div key={i} className="flex gap-3 items-start">
              <span className="badge-purple shrink-0 mt-0.5">{agent}</span>
              <p className="text-gray-300 text-sm leading-relaxed">{tip}</p>
            </div>
          ))}
        </div>
      </div>

      {/* How the Mentor works */}
      <div className="card space-y-2 text-sm text-gray-400">
        <h2 className="text-sm font-semibold text-gray-300">How the Mentor Agent Works</h2>
        <p>The Mentor is the last agent to speak in every debate. It synthesises all prior agent feedback — Trend signals, Brand compliance, Risk assessment, and CMO decision — into actionable coaching notes.</p>
        <p>It specifically looks for tension between agents (e.g. Trend says "go bold" while Risk flags it) and offers balanced guidance that can improve the next campaign iteration.</p>
        <p>Mentor feedback is saved to the Agent Logs table for every session — browse them via the <span className="text-brand-400">Engagement Console</span> after running a campaign.</p>
      </div>
    </div>
  )
}
