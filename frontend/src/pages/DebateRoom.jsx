import { useState, useCallback, useRef, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useCampaign } from '../hooks/useApi'
import { useDebateSocket } from '../hooks/useDebateSocket'

const AGENT_META = {
  trend:      { color: '#6366f1', label: 'Trend' },
  brand:      { color: '#10b981', label: 'Brand' },
  risk:       { color: '#ef4444', label: 'Risk' },
  engagement: { color: '#f59e0b', label: 'Engagement' },
  cmo:        { color: '#8b5cf6', label: 'CMO' },
  mentor:     { color: '#06b6d4', label: 'Mentor' },
}

const STAGE_LABELS = {
  trend_analysis:    'Trend Analysis',
  brand_review:      'Brand Review',
  risk_assessment:   'Risk Assessment',
  engagement_review: 'Engagement Review',
  cmo_decision:      'CMO Decision',
  content_generation:'Content Generation',
  mentor_review:     'Mentor Review',
}

function AgentBubble({ event }) {
  const agent = event.agent?.toLowerCase()
  const meta  = AGENT_META[agent] ?? { color: '#6b7280', label: event.agent ?? 'System' }

  return (
    <div className="flex gap-3 group">
      <div
        className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center text-xs font-bold text-white"
        style={{ background: meta.color }}
      >
        {meta.label[0]}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="text-xs font-semibold" style={{ color: meta.color }}>{meta.label}</span>
          {event.stage && (
            <span className="badge-gray text-[10px]">{STAGE_LABELS[event.stage] ?? event.stage}</span>
          )}
        </div>
        <div className="bg-gray-800/60 border border-gray-700/50 rounded-lg px-3 py-2 text-sm text-gray-200 leading-relaxed">
          {event.message ?? event.content ?? JSON.stringify(event)}
        </div>
        {event.confidence !== undefined && (
          <p className="text-xs text-gray-500 mt-0.5">confidence: {(event.confidence * 100).toFixed(0)}%</p>
        )}
      </div>
    </div>
  )
}

function SystemBubble({ event }) {
  const isBluesky  = event.type === 'bluesky_published'
  const isApproved = event.type === 'content_approved' || event.outcome === 'approved'
  const isRejected = event.outcome === 'rejected'

  return (
    <div className={`text-center py-1.5 px-4 rounded-full text-xs mx-auto w-fit border ${
      isBluesky  ? 'bg-blue-900/30 border-blue-700 text-blue-300' :
      isApproved ? 'bg-emerald-900/30 border-emerald-700 text-emerald-300' :
      isRejected ? 'bg-red-900/30 border-red-700 text-red-300' :
                   'bg-gray-800 border-gray-700 text-gray-400'
    }`}>
      {event.message ?? event.type}
      {event.web_url && (
        <a href={event.web_url} target="_blank" rel="noopener noreferrer" className="ml-2 underline">view post</a>
      )}
    </div>
  )
}

export default function DebateRoom() {
  const { id }    = useParams()
  const navigate  = useNavigate()
  const { data: campaign } = useCampaign(id)
  const [events, setEvents] = useState([])
  const [stage,  setStage]  = useState(null)
  const [done,   setDone]   = useState(false)
  const bottomRef = useRef(null)

  const onEvent = useCallback((event) => {
    setEvents(prev => [...prev, event])
    if (event.stage) setStage(event.stage)
    if (event.type === 'debate_complete' || event.type === 'debate_error') setDone(true)
  }, [])

  useDebateSocket(done ? null : id, onEvent, {
    brand_name:  campaign?.brand_name  || 'Brand',
    brand_voice: campaign?.brand_voice || 'professional and engaging',
  })

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events])

  const STAGES = Object.keys(STAGE_LABELS)
  const currentIdx = STAGES.indexOf(stage)

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-gray-800 px-6 py-4 flex items-center gap-4">
        <button onClick={() => navigate('/dashboard')} className="text-gray-500 hover:text-gray-300 text-sm">← Back</button>
        <div className="flex-1">
          <h1 className="text-lg font-semibold text-white">{campaign?.title ?? 'Debate Room'}</h1>
          <p className="text-gray-400 text-xs">Live AI Council Debate</p>
        </div>
        {done && <span className="badge-green">Complete</span>}
        {!done && <span className="badge-yellow animate-pulse">Live</span>}
      </div>

      {/* Stage progress bar */}
      <div className="px-6 py-3 border-b border-gray-800 flex gap-1.5">
        {STAGES.map((s, i) => (
          <div
            key={s}
            title={STAGE_LABELS[s]}
            className={`h-1.5 flex-1 rounded-full transition-colors ${
              i < currentIdx  ? 'bg-brand-600' :
              i === currentIdx ? 'bg-brand-400 animate-pulse' :
                                 'bg-gray-800'
            }`}
          />
        ))}
      </div>

      {/* Feed */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
        {events.length === 0 && (
          <p className="text-gray-500 text-sm text-center mt-8">Waiting for agents to begin…</p>
        )}
        {events.map((ev, i) => {
          const isAgent = !!ev.agent
          return isAgent
            ? <AgentBubble  key={i} event={ev} />
            : <SystemBubble key={i} event={ev} />
        })}
        <div ref={bottomRef} />
      </div>

      {/* Content preview if debate is done */}
      {done && events.some(e => e.type === 'content_generated') && (
        <div className="border-t border-gray-800 px-6 py-4">
          <p className="text-xs text-gray-400 mb-2">Generated content available in <button className="text-brand-400 underline" onClick={() => navigate('/dashboard')}>Dashboard</button>.</p>
        </div>
      )}
    </div>
  )
}
