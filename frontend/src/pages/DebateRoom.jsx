import { useState, useCallback, useRef, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useCampaign } from '../hooks/useApi'
import { useDebateSocket } from '../hooks/useDebateSocket'
import axios from 'axios'

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

const BSKY_MAX = 300

// ── Sub-components ───────────────────────────────────────────────

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
  const isBluesky  = event.type === 'bluesky_published' || event.stage === 'bluesky_publish'
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
      {(event.web_url || event.extra?.web_url) && (
        <a
          href={event.web_url || event.extra?.web_url}
          target="_blank"
          rel="noopener noreferrer"
          className="ml-2 underline"
        >
          view post
        </a>
      )}
    </div>
  )
}

// ── Reject Feedback Modal ────────────────────────────────────────

function RejectModal({ sessionId, onNewDraft, onClose }) {
  const [feedback, setFeedback] = useState('')
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState(null)

  async function handleSubmit() {
    setLoading(true)
    setError(null)
    try {
      const res = await axios.post(`/api/v1/debates/${sessionId}/reject`, {
        feedback: feedback.trim(),
      })
      // Backend re-ran content generation and returned a new draft + image
      onNewDraft(res.data.draft_post ?? '', res.data.image_b64 ?? '')
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Failed to regenerate content. Try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-md shadow-2xl">
        {/* Header */}
        <div className="px-6 pt-5 pb-4 border-b border-gray-800">
          <h2 className="text-white font-semibold text-base">Tell us what to improve</h2>
          <p className="text-gray-400 text-xs mt-0.5">
            Your feedback will be sent to the AI Council. They'll generate a revised post for your review.
          </p>
        </div>

        {/* Feedback input */}
        <div className="px-6 pt-4 pb-2">
          <textarea
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-gray-200 
                       placeholder-gray-500 outline-none focus:border-gray-500 resize-none min-h-[100px]"
            placeholder="e.g. Make it more energetic, focus on the price offer, add a question to drive engagement…"
            value={feedback}
            onChange={e => setFeedback(e.target.value)}
            disabled={loading}
            autoFocus
          />
          <p className="text-gray-600 text-xs mt-1">
            Leave blank to regenerate without specific feedback.
          </p>
        </div>

        {/* Error */}
        {error && (
          <p className="mx-6 mb-2 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
            {error}
          </p>
        )}

        {/* Actions */}
        <div className="px-6 py-5 flex gap-3 justify-end">
          <button
            onClick={onClose}
            disabled={loading}
            className="px-4 py-2 rounded-lg border border-gray-700 text-gray-300 text-sm hover:bg-gray-800 disabled:opacity-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="px-5 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-medium disabled:opacity-50 transition-colors"
          >
            {loading ? 'Regenerating…' : 'Regenerate Post'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Approval Modal ───────────────────────────────────────────────

function ApprovalModal({ sessionId, draftPost, imageB64, onApproved, onReject }) {
  const [text, setText]       = useState(draftPost ?? '')
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)

  // Keep text in sync if a new draft arrives (after re-debate)
  useEffect(() => { setText(draftPost ?? '') }, [draftPost])

  const charCount = [...text].length   // spread gives approximate grapheme count
  const overLimit = charCount > BSKY_MAX

  async function handleApprove() {
    if (!text.trim() || overLimit) return
    setLoading(true)
    setError(null)
    try {
      const res = await axios.post(`/api/v1/debates/${sessionId}/approve`, {
        post_text: text,
      })
      onApproved(res.data)
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Publish failed. Try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg shadow-2xl">
        {/* Header */}
        <div className="px-6 pt-5 pb-4 border-b border-gray-800">
          <h2 className="text-white font-semibold text-base">Review & Approve Post</h2>
          <p className="text-gray-400 text-xs mt-0.5">
            Your AI Council has prepared this Bluesky post. Edit if needed, then approve or reject.
          </p>
        </div>

        {/* Bluesky post preview card */}
        <div className="px-6 pt-4">
          <div className="bg-[#0a0a14] border border-[#1e3a5f] rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white text-xs font-bold">
                B
              </div>
              <div>
                <p className="text-white text-xs font-semibold leading-none">Your Brand</p>
                <p className="text-blue-400 text-[11px]">@irfan28i.bsky.social</p>
              </div>
            </div>
            {/* Editable post text */}
            <textarea
              className={`w-full bg-transparent text-sm leading-relaxed resize-none outline-none min-h-[120px] ${
                overLimit ? 'text-red-400' : 'text-gray-200'
              }`}
              value={text}
              onChange={e => setText(e.target.value)}
              placeholder="Post text will appear here…"
              disabled={loading}
            />
            {/* AI-generated image preview */}
            {imageB64 && (
              <div className="mt-3 rounded-lg overflow-hidden border border-[#1e3a5f]">
                <img
                  src={`data:image/png;base64,${imageB64}`}
                  alt="AI-generated post image"
                  className="w-full object-cover max-h-64"
                />
              </div>
            )}
            {/* Character counter */}
            <div className={`text-right text-xs mt-1 font-medium ${overLimit ? 'text-red-400' : 'text-gray-500'}`}>
              {charCount} / {BSKY_MAX}
            </div>
          </div>
        </div>

        {/* Error */}
        {error && (
          <p className="mx-6 mt-3 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
            {error}
          </p>
        )}

        {/* Actions */}
        <div className="px-6 py-5 flex gap-3 justify-end">
          <button
            onClick={onReject}
            disabled={loading}
            className="px-4 py-2 rounded-lg border border-gray-700 text-gray-300 text-sm hover:bg-gray-800 disabled:opacity-50 transition-colors"
          >
            Reject & Revise
          </button>
          <button
            onClick={handleApprove}
            disabled={loading || overLimit || !text.trim()}
            className="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium disabled:opacity-50 transition-colors"
          >
            {loading ? 'Publishing…' : 'Approve & Publish'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────

export default function DebateRoom() {
  const { id }   = useParams()
  const navigate = useNavigate()
  const { data: campaign } = useCampaign(id)

  const [events,          setEvents]          = useState([])
  const [stage,           setStage]           = useState(null)
  const [done,            setDone]            = useState(false)
  const [sessionId,       setSessionId]       = useState(null)
  // modal state: null | 'approval' | 'reject'
  const [modal,           setModal]           = useState(null)
  const [draftPost,       setDraftPost]       = useState('')
  const [imageB64,        setImageB64]        = useState('')
  const [revisionCount,   setRevisionCount]   = useState(0)
  const bottomRef = useRef(null)

  const onEvent = useCallback((event) => {
    if (event.type === 'session_created') {
      setSessionId(event.session_id)
      return
    }

    if (event.type === 'pending_approval') {
      setDraftPost(event.draft_post ?? '')
      setImageB64(event.image_b64 ?? '')
      setModal('approval')
      setEvents(prev => [...prev, {
        type:    'system',
        message: revisionCount > 0
          ? `Revised post ready (attempt ${revisionCount + 1}) — awaiting your approval.`
          : 'Content ready — awaiting your approval before publishing to Bluesky.',
        stage:   'human_approval',
      }])
      return
    }

    setEvents(prev => [...prev, event])
    if (event.stage) setStage(event.stage)
    if (event.type === 'debate_complete' || event.type === 'debate_error') setDone(true)
  }, [revisionCount])

  useDebateSocket(done ? null : id, onEvent, {
    brand_name:  campaign?.brand_name  || 'Brand',
    brand_voice: campaign?.brand_voice || 'professional and engaging',
  })

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events])

  // Approve → publish and close
  function handleApproved(data) {
    setModal(null)
    setDone(true)
    setEvents(prev => [...prev, {
      type:    'bluesky_published',
      stage:   'bluesky_publish',
      message: 'Published to Bluesky!',
      web_url: data.web_url,
      extra:   { web_url: data.web_url },
    }])
  }

  // User clicks "Reject & Revise" in approval modal → show feedback modal
  function handleRejectClick() {
    setModal('reject')
  }

  // Backend returned a new draft after rejection+feedback → show approval modal again
  function handleNewDraft(newDraft, newImageB64 = '') {
    setRevisionCount(c => c + 1)
    setDraftPost(newDraft)
    setImageB64(newImageB64)
    setModal('approval')
    setEvents(prev => [...prev, {
      type:    'system',
      message: 'AI Council revised the post based on your feedback.',
      stage:   'human_approval',
    }])
  }

  // User cancels the reject feedback modal → go back to approval modal
  function handleCancelReject() {
    setModal('approval')
  }

  const STAGES     = Object.keys(STAGE_LABELS)
  const currentIdx = STAGES.indexOf(stage)
  const activeSession = sessionId   // the DB session id used for approve/reject

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-gray-800 px-6 py-4 flex items-center gap-4">
        <button onClick={() => navigate('/dashboard')} className="text-gray-500 hover:text-gray-300 text-sm">
          ← Back
        </button>
        <div className="flex-1">
          <h1 className="text-lg font-semibold text-white">{campaign?.title ?? 'Debate Room'}</h1>
          <p className="text-gray-400 text-xs">Live AI Council Debate</p>
        </div>
        {done && !modal && <span className="badge-green">Complete</span>}
        {modal === 'approval' && <span className="badge-yellow animate-pulse">Awaiting Approval</span>}
        {modal === 'reject'   && <span className="badge-yellow animate-pulse">Regenerating…</span>}
        {!done && !modal && <span className="badge-yellow animate-pulse">Live</span>}
      </div>

      {/* Stage progress bar */}
      <div className="px-6 py-3 border-b border-gray-800 flex gap-1.5">
        {STAGES.map((s, i) => (
          <div
            key={s}
            title={STAGE_LABELS[s]}
            className={`h-1.5 flex-1 rounded-full transition-colors ${
              i < currentIdx   ? 'bg-brand-600' :
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
        {events.map((ev, i) => (
          ev.agent
            ? <AgentBubble  key={i} event={ev} />
            : <SystemBubble key={i} event={ev} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Content preview footer */}
      {done && !modal && events.some(e => e.type === 'content_generated') && (
        <div className="border-t border-gray-800 px-6 py-4">
          <p className="text-xs text-gray-400">
            Generated content available in{' '}
            <button className="text-brand-400 underline" onClick={() => navigate('/dashboard')}>
              Dashboard
            </button>.
          </p>
        </div>
      )}

      {/* Modals */}
      {modal === 'approval' && (
        <ApprovalModal
          sessionId={activeSession}
          draftPost={draftPost}
          imageB64={imageB64}
          onApproved={handleApproved}
          onReject={handleRejectClick}
        />
      )}
      {modal === 'reject' && (
        <RejectModal
          sessionId={activeSession}
          onNewDraft={handleNewDraft}
          onClose={handleCancelReject}
        />
      )}
    </div>
  )
}
