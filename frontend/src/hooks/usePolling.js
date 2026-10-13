import { useEffect, useRef } from 'react'

// One lifecycle-safe polling primitive for API-backed cross-session refreshes.
export default function usePolling(callback, intervalMs) {
  const callbackRef = useRef(callback)

  useEffect(() => {
    callbackRef.current = callback
  }, [callback])

  useEffect(() => {
    if (intervalMs == null) return undefined
    const timer = setInterval(() => callbackRef.current(), intervalMs)
    return () => clearInterval(timer)
  }, [intervalMs])
}
