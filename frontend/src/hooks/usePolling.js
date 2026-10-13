import { useEffect, useRef } from 'react'

// Lifecycle-safe polling for API-backed cross-session refreshes. Poll only while
// the page is visible, and refresh as soon as a user returns to the app.
export default function usePolling(callback, intervalMs) {
  const callbackRef = useRef(callback)

  useEffect(() => {
    callbackRef.current = callback
  }, [callback])

  useEffect(() => {
    if (intervalMs == null) return undefined

    let timer
    let inFlight = false
    let lastRunAt = 0

    const run = async (force = false) => {
      if (document.visibilityState === 'hidden' || inFlight) return
      // Focus and visibility can fire together; collapse those into one request.
      if (!force && Date.now() - lastRunAt < 500) return
      inFlight = true
      lastRunAt = Date.now()
      try {
        await callbackRef.current()
      } finally {
        inFlight = false
      }
    }

    const schedule = () => {
      timer = window.setTimeout(async () => {
        try {
          await run()
        } finally {
          schedule()
        }
      }, intervalMs)
    }
    const refreshOnReturn = () => {
      if (document.visibilityState !== 'hidden') run(true)
    }

    schedule()
    window.addEventListener('focus', refreshOnReturn)
    window.addEventListener('online', refreshOnReturn)
    document.addEventListener('visibilitychange', refreshOnReturn)

    return () => {
      window.clearTimeout(timer)
      window.removeEventListener('focus', refreshOnReturn)
      window.removeEventListener('online', refreshOnReturn)
      document.removeEventListener('visibilitychange', refreshOnReturn)
    }
  }, [intervalMs])
}
