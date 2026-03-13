import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCreateCampaign, useRunCampaign } from '../hooks/useApi'

const PLATFORMS = ['instagram','twitter','tiktok','youtube','linkedin','facebook']
const GOALS = ['brand_awareness','lead_generation','engagement','sales','community_building','thought_leadership']

export default function CampaignBuilder() {
  const navigate      = useNavigate()
  const createCampaign = useCreateCampaign()
  const runCampaign    = useRunCampaign()

  const [form, setForm] = useState({
    title:           '',
    description:     '',
    brand_name:      '',
    brand_voice:     'professional and engaging',
    goal:            'brand_awareness',
    target_audience: '',
    brand_guidelines:'',
    keywords:        '',
    platforms:       ['instagram','twitter'],
    auto_run:        true,
  })
  const [error, setError] = useState(null)

  const toggle = (platform) => {
    setForm(f => ({
      ...f,
      platforms: f.platforms.includes(platform)
        ? f.platforms.filter(p => p !== platform)
        : [...f.platforms, platform],
    }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      const body = {
        ...form,
        keywords: form.keywords.split(',').map(k => k.trim()).filter(Boolean),
      }
      const campaign = await createCampaign.mutateAsync(body)

      if (form.auto_run) {
        await runCampaign.mutateAsync({
          id:          campaign.id,
          brand_name:  form.brand_name || form.title,
          brand_voice: form.brand_voice,
        })
        navigate(`/campaigns/${campaign.id}/debate`)
      } else {
        navigate('/dashboard')
      }
    } catch (err) {
      setError(err.message)
    }
  }

  const busy = createCampaign.isPending || runCampaign.isPending

  return (
    <div className="p-6 max-w-2xl">
      <h1 className="text-2xl font-bold text-white mb-1">New Campaign</h1>
      <p className="text-gray-400 text-sm mb-6">Brief the AI Council and watch them debate your strategy.</p>

      {error && (
        <div className="bg-red-900/30 border border-red-700 text-red-300 rounded-lg p-3 mb-4 text-sm">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Campaign title */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">Campaign Title *</label>
          <input
            required
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
            placeholder="e.g. Summer 2026 Brand Push"
            value={form.title}
            onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
          />
        </div>

        {/* Brand name */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">Brand Name *</label>
          <input
            required
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
            placeholder="e.g. Acme Corp"
            value={form.brand_name}
            onChange={e => setForm(f => ({ ...f, brand_name: e.target.value }))}
          />
        </div>

        {/* Brand voice */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">Brand Voice</label>
          <input
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
            placeholder="e.g. witty and approachable"
            value={form.brand_voice}
            onChange={e => setForm(f => ({ ...f, brand_voice: e.target.value }))}
          />
        </div>

        {/* Goal */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">Campaign Goal</label>
          <select
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
            value={form.goal}
            onChange={e => setForm(f => ({ ...f, goal: e.target.value }))}
          >
            {GOALS.map(g => (
              <option key={g} value={g}>{g.replace(/_/g, ' ')}</option>
            ))}
          </select>
        </div>

        {/* Target audience */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">Target Audience</label>
          <input
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
            placeholder="e.g. Gen Z tech enthusiasts, 18-25"
            value={form.target_audience}
            onChange={e => setForm(f => ({ ...f, target_audience: e.target.value }))}
          />
        </div>

        {/* Description */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">Campaign Brief</label>
          <textarea
            rows={3}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500 resize-none"
            placeholder="What's the campaign about? Key messages?"
            value={form.description}
            onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
          />
        </div>

        {/* Keywords */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">Keywords <span className="text-gray-500">(comma-separated)</span></label>
          <input
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
            placeholder="e.g. innovation, sustainability, growth"
            value={form.keywords}
            onChange={e => setForm(f => ({ ...f, keywords: e.target.value }))}
          />
        </div>

        {/* Platforms */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">Platforms</label>
          <div className="flex flex-wrap gap-2">
            {PLATFORMS.map(p => (
              <button
                key={p}
                type="button"
                onClick={() => toggle(p)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  form.platforms.includes(p)
                    ? 'bg-brand-600/30 border-brand-500 text-brand-300'
                    : 'bg-gray-800 border-gray-700 text-gray-400 hover:text-gray-200'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        {/* Auto-run toggle */}
        <label className="flex items-center gap-3 cursor-pointer">
          <div
            onClick={() => setForm(f => ({ ...f, auto_run: !f.auto_run }))}
            className={`w-10 h-5 rounded-full transition-colors ${form.auto_run ? 'bg-brand-600' : 'bg-gray-700'} relative`}
          >
            <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${form.auto_run ? 'translate-x-5' : 'translate-x-0.5'}`} />
          </div>
          <span className="text-sm text-gray-300">Immediately start AI Council debate</span>
        </label>

        {/* Submit */}
        <button type="submit" disabled={busy} className="btn-primary w-full py-2.5">
          {busy ? 'Starting…' : form.auto_run ? 'Create & Run Debate' : 'Create Campaign'}
        </button>
      </form>
    </div>
  )
}
