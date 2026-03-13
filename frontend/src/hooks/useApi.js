import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { campaignsApi, debatesApi, contentApi, analyticsApi } from '../services/api'

// ── Campaigns ─────────────────────────────────────────────────
export function useCampaigns(params) {
  return useQuery({
    queryKey: ['campaigns', params],
    queryFn: () => campaignsApi.list(params).then(r => r.data),
  })
}

export function useCampaign(id) {
  return useQuery({
    queryKey: ['campaign', id],
    queryFn: () => campaignsApi.get(id).then(r => r.data),
    enabled: !!id,
  })
}

export function useCreateCampaign() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => campaignsApi.create(body).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['campaigns'] }),
  })
}

export function useUpdateCampaign() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }) => campaignsApi.update(id, body).then(r => r.data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: ['campaigns'] })
      qc.invalidateQueries({ queryKey: ['campaign', id] })
    },
  })
}

export function useRunCampaign() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...params }) => campaignsApi.run(id, params).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['campaigns'] }),
  })
}

// ── Debates ───────────────────────────────────────────────────
export function useDebates(campaignId) {
  return useQuery({
    queryKey: ['debates', campaignId],
    queryFn: () => debatesApi.list(campaignId).then(r => r.data),
    enabled: !!campaignId,
  })
}

export function useDebateLogs(sessionId) {
  return useQuery({
    queryKey: ['debate-logs', sessionId],
    queryFn: () => debatesApi.getLogs(sessionId).then(r => r.data),
    enabled: !!sessionId,
    refetchInterval: 3000,
  })
}

// ── Content ───────────────────────────────────────────────────
export function useContent(params) {
  return useQuery({
    queryKey: ['content', params],
    queryFn: () => contentApi.list(params).then(r => r.data),
  })
}

export function usePublishContent() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => contentApi.publish(id).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['content'] }),
  })
}

// ── Analytics ─────────────────────────────────────────────────
export function useAnalyticsSummary(params) {
  return useQuery({
    queryKey: ['analytics-summary', params],
    queryFn: () => analyticsApi.summary(params).then(r => r.data),
    staleTime: 60_000,
  })
}

export function useBlueskyAnalytics() {
  return useQuery({
    queryKey: ['analytics-bluesky'],
    queryFn: () => analyticsApi.bluesky().then(r => r.data),
    staleTime: 60_000,
  })
}

export function useTopContent(params) {
  return useQuery({
    queryKey: ['analytics-top-content', params],
    queryFn: () => analyticsApi.topContent(params).then(r => r.data),
    staleTime: 60_000,
  })
}

export function useAgentStats(params) {
  return useQuery({
    queryKey: ['analytics-agent-stats', params],
    queryFn: () => analyticsApi.agentStats(params).then(r => r.data),
    staleTime: 60_000,
  })
}
