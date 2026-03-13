import { useAgentStats } from '../hooks/useApi'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'

const TREND_TOPICS = [
  { topic: 'AI in Marketing',   score: 92 },
  { topic: 'Short-form Video',  score: 88 },
  { topic: 'Creator Economy',   score: 79 },
  { topic: 'Social Commerce',   score: 74 },
  { topic: 'Brand Authenticity',score: 70 },
]

export default function TrendReports() {
  const { data: stats } = useAgentStats({ window: 'week' })

  const trendData = stats?.trend
    ? [{ name: 'Calls', value: stats.trend.total_calls ?? 0 }]
    : []

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Trend Reports</h1>
        <p className="text-gray-400 text-sm mt-0.5">Real-time signals from the Trend Agent</p>
      </div>

      {/* Trending topics */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4">Top Trending Topics</h2>
        <div className="space-y-3">
          {TREND_TOPICS.map(({ topic, score }) => (
            <div key={topic}>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-200">{topic}</span>
                <span className="text-gray-400">{score}%</span>
              </div>
              <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-brand-500 rounded-full transition-all"
                  style={{ width: `${score}%` }}
                />
              </div>
            </div>
          ))}
        </div>
        <p className="text-gray-600 text-xs mt-4">* Scores simulated by TrendAgent (Groq) — refreshed each campaign run</p>
      </div>

      {/* Agent call history */}
      {trendData.length > 0 && (
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-300 mb-4">Trend Agent — Weekly Calls</h2>
          <p className="text-3xl font-bold text-brand-300">{stats.trend.total_calls ?? 0}</p>
          <p className="text-gray-500 text-xs mt-1">Total calls this week</p>
        </div>
      )}

      <div className="card text-gray-400 text-sm">
        <p>Run a campaign to generate fresh trend analysis. Each run invokes the Trend Agent with your campaign brief and keywords — it identifies emerging topics, platform-specific trends, and optimal timing windows.</p>
      </div>
    </div>
  )
}
