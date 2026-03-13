import { useAgentStats } from '../hooks/useApi'
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer } from 'recharts'

const DIMENSIONS = ['Voice Consistency','Visual Identity','Tone Alignment','Message Clarity','Audience Fit']

export default function BrandHealth() {
  const { data: stats } = useAgentStats({ window: 'week' })
  const brandStats = stats?.brand ?? {}

  const radarData = DIMENSIONS.map(d => ({
    dimension: d,
    score:     Math.floor(60 + Math.random() * 35),
  }))

  const approvalRate = brandStats.total_calls
    ? Math.round(((brandStats.approved ?? 0) / brandStats.total_calls) * 100)
    : null

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Brand Health Monitor</h1>
        <p className="text-gray-400 text-sm mt-0.5">Brand Agent signals — tone, consistency, audience alignment</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="card text-center">
          <p className="text-3xl font-bold text-emerald-400">{approvalRate !== null ? `${approvalRate}%` : '—'}</p>
          <p className="text-gray-400 text-xs mt-1">Brand Approval Rate</p>
        </div>
        <div className="card text-center">
          <p className="text-3xl font-bold text-brand-300">{brandStats.total_calls ?? '—'}</p>
          <p className="text-gray-400 text-xs mt-1">Brand Reviews (week)</p>
        </div>
        <div className="card text-center">
          <p className="text-3xl font-bold text-red-400">{brandStats.rejected ?? '—'}</p>
          <p className="text-gray-400 text-xs mt-1">Rejected for Brand Issues</p>
        </div>
      </div>

      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4">Brand Dimensions Radar</h2>
        <ResponsiveContainer width="100%" height={260}>
          <RadarChart data={radarData}>
            <PolarGrid stroke="#374151" />
            <PolarAngleAxis dataKey="dimension" tick={{ fill: '#9ca3af', fontSize: 11 }} />
            <Radar dataKey="score" fill="#6366f1" fillOpacity={0.3} stroke="#6366f1" strokeWidth={2} />
          </RadarChart>
        </ResponsiveContainer>
        <p className="text-gray-600 text-xs mt-2">* Simulated scores for demo — real scores come from Brand Agent feedback</p>
      </div>

      <div className="card text-gray-400 text-sm">
        <p>The Brand Agent reviews every draft against your brand guidelines, voice, and visual identity rules. Run more campaigns to build a richer health history.</p>
      </div>
    </div>
  )
}
