import { useEffect, useRef, useCallback } from 'react'

/**
 * useDebateSocket — opens a native WebSocket to the backend debate stream.
 *
 * @param {string|null} campaignId  - campaign UUID; hook is inactive when null
 * @param {function}    onEvent     - called with each parsed event object
 * @param {object}      [params]    - optional query params forwarded to the WS URL
 * @returns {{ close: function }} - imperative handle to close the socket
 */
export function useDebateSocket(campaignId, onEvent, params = {}) {
  const wsRef      = useRef(null)
  const onEventRef = useRef(onEvent)

  // Keep the callback ref fresh without restarting the socket
  useEffect(() => { onEventRef.current = onEvent }, [onEvent])

  useEffect(() => {
    if (!campaignId) return

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const host     = window.location.hostname
    const port     = import.meta.env.VITE_API_PORT || '8000'

    // Build query string from params (filter out undefined/null/empty)
    const qs = Object.entries(params)
      .filter(([, v]) => v != null && v !== '')
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
      .join('&')

    const url = `${protocol}://${host}:${port}/api/v1/debates/${campaignId}/stream${qs ? '?' + qs : ''}`

    console.log('[WS] Connecting to', url)
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen    = () => console.log('[WS] Connected to debate stream', campaignId)
    ws.onclose   = (e) => console.log('[WS] Closed', e.code, e.reason)
    ws.onerror   = (e) => console.error('[WS] Error', e)
    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data)
        onEventRef.current?.(event)
      } catch {
        console.warn('[WS] Non-JSON message', e.data)
      }
    }

    return () => {
      ws.close(1000, 'component unmounted')
      wsRef.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaignId])

  const close = useCallback(() => {
    wsRef.current?.close(1000, 'manual close')
  }, [])

  return { close }
}
