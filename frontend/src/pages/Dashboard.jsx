import { useNavigate } from 'react-router-dom'
import { useCampaigns, useRunCampaign } from '../hooks/useApi'
import { useAgentStats, useBlueskyAnalytics } from '../hooks/useApi'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

const STATUS_BADGE = {
  draft:     'badge-gray',
  debating:  'badge-yellow',
  approved:  'badge-green',
  rejected:  'badge-red',
  published: 'badge-blue',
  archived:  'badge-gray',
}

const AGENT_COLORS = {
  trend:      '#6366f1',
  brand:      '#10b981',
  risk:       '#ef4444',
  engagement: '#f59e0b',
  cmo:        '#8b5cf6',
  mentor:     '#06b6d4',
}

export default function Dashboard() {
  const navigate   = useNavigate()
  const { data: campaigns, isLoading } = useCampaigns({ page_size: 10 })
  const { data: agentStats }  = useAgentStats({ window: 'day' })
  const { data: bluesky }     = useBlueskyAnalytics()
  const runCampaign = useRunCampaign()

  const items = campaigns?.items ?? []

  const handleRun = async (campaign) => {
    if (['debating', 'archived'].includes(campaign.status)) return
    await runCampaign.mutateAsync({
      id:          campaign.id,
      brand_name:  campaign.title,
      brand_voice: 'professional and engaging',
    })
    navigate(`/campaigns/${campaign.id}/debate`)
  }

  const chartData = agentStats
    ? Object.entries(agentStats).map(([name, stats]) => ({
        name: name.charAt(0).toUpperCase() + name.slice(1),
        calls:    stats.total_calls   ?? 0,
        approved: stats.approved      ?? 0,
      }))
    : []

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-gray-400 text-sm mt-0.5">AI Council — Multi-Agent Social Media Strategy</p>
        </div>
        <button className="btn-primary" onClick={() => navigate('/campaigns/new')}>
          + New Campaign
        </button>
      </div>

      {/* Bluesky summary */}
      {bluesky && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: 'Posts Published', value: bluesky.total_posts ?? 0 },
            { label: 'Total Likes',     value: bluesky.total_likes ?? 0 },
            { label: 'Total Reposts',   value: bluesky.total_reposts ?? 0 },
            { label: 'Total Replies',   value: bluesky.total_replies ?? 0 },
          ].map(({ label, value }) => (
            <div key={label} className="card text-center">
              <p className="text-3xl font-bold text-brand-300">{value}</p>
              <p className="text-gray-400 text-xs mt-1">{label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Agent call chart */}
      {chartData.length > 0 && (
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-300 mb-4">Agent Activity (today)</h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={chartData} barGap={4}>
              <XAxis dataKey="name" tick={{ fill: '#6b7280', fontSize: 11 }} />
              <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                labelStyle={{ color: '#e5e7eb' }}
              />
              <Bar dataKey="calls" radius={[4,4,0,0]}>
                {chartData.map((entry) => (
                  <Cell key={entry.name} fill={AGENT_COLORS[entry.name.toLowerCase()] ?? '#6366f1'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Campaign list */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4">Campaigns</h2>
        {isLoading ? (
          <p className="text-gray-500 text-sm">Loading…</p>
        ) : items.length === 0 ? (
          <p className="text-gray-500 text-sm">No campaigns yet. <button className="text-brand-400 underline" onClick={() => navigate('/campaigns/new')}>Create one</button>.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 text-xs border-b border-gray-800">
                <th className="pb-2 text-left">Title</th>
                <th className="pb-2 text-left">Goal</th>
                <th className="pb-2 text-left">Status</th>
                <th className="pb-2 text-left">Platforms</th>
                <th className="pb-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/50">
              {items.map((c) => (
                <tr key={c.id} className="hover:bg-gray-800/30 transition-colors">
                  <td className="py-2.5 pr-4 font-medium text-gray-200">{c.title}</td>
                  <td className="py-2.5 pr-4 text-gray-400">{c.goal}</td>
                  <td className="py-2.5 pr-4">
                    <span className={STATUS_BADGE[c.status] ?? 'badge-gray'}>{c.status}</span>
                  </td>
                  <td className="py-2.5 pr-4 text-gray-500">{(c.platforms ?? []).join(', ')}</td>
                  <td className="py-2.5 text-right space-x-2">
                    {c.status === 'debating' && (
                      <button
                        className="text-brand-400 text-xs hover:underline"
                        onClick={() => navigate(`/campaigns/${c.id}/debate`)}
                      >
                        Watch
                      </button>
                    )}
                    <button
                      className="btn-primary text-xs py-1 px-3"
                      disabled={['debating','archived'].includes(c.status) || runCampaign.isPending}
                      onClick={() => handleRun(c)}
                    >
                      Run
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
