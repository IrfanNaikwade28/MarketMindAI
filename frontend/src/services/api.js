import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30_000,
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg = err.response?.data?.detail || err.message || 'Unknown error'
    console.error('[API Error]', msg)
    return Promise.reject(new Error(msg))
  }
)

// ── Campaigns ──────────────────────────────────────────────────
export const campaignsApi = {
  list:   (params) => api.get('/campaigns', { params }),
  get:    (id)     => api.get(`/campaigns/${id}`),
  create: (body)   => api.post('/campaigns', body),
  update: (id, b)  => api.patch(`/campaigns/${id}`, b),
  remove: (id)     => api.delete(`/campaigns/${id}`),
  run:    (id, params) => api.post(`/campaigns/${id}/run`, null, { params }),
}

// ── Debates ────────────────────────────────────────────────────
export const debatesApi = {
  list:      (campaignId) => api.get(`/debates/${campaignId}`),
  getLatest: (campaignId) => api.get(`/debates/${campaignId}/latest`),
  getLogs:   (sessionId)  => api.get(`/debates/${sessionId}/logs`),
}

// ── Content ────────────────────────────────────────────────────
export const contentApi = {
  list:    (params) => api.get('/content', { params }),
  get:     (id)     => api.get(`/content/${id}`),
  publish: (id)     => api.post(`/content/${id}/publish`),
  approve: (id)     => api.patch(`/content/${id}`, { status: 'approved' }),
}

// ── Analytics ──────────────────────────────────────────────────
export const analyticsApi = {
  summary:       (params) => api.get('/analytics/summary', { params }),
  bluesky:       ()       => api.get('/analytics/bluesky'),
  syncBluesky:   ()       => api.post('/analytics/bluesky/sync'),
  topContent:    (params) => api.get('/analytics/top-content', { params }),
  agentStats:    (params) => api.get('/analytics/agent-stats', { params }),
}

export default api
