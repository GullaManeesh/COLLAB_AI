
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ArrowDown, CheckCircle2, CircleAlert, LoaderCircle, Send, Wifi, WifiOff } from 'lucide-react'
import api from '../api/client'
import { useAuth } from '../context/AuthContext'

const getErrorMessage = (error) =>
  error?.response?.data?.detail || error?.message || 'Something went wrong.'

function mergeMessages(current, incoming) {
  const byId = new Map(current.map((message) => [message.id, message]))

  for (const message of incoming) {
    if (message?.id) byId.set(message.id, message)
  }

  return [...byId.values()].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  )
}

function formatTime(value) {
  if (!value) return ''
  return new Date(value).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function Chat() {
  const { id: workspaceId } = useParams()
  const { user } = useAuth()

  const [messages, setMessages] = useState([])
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [connection, setConnection] = useState('connecting')
  const [error, setError] = useState('')
  const [showScrollButton, setShowScrollButton] = useState(false)

  const socketRef = useRef(null)
  const reconnectTimerRef = useRef(null)
  const reconnectAttemptsRef = useRef(0)
  const shouldReconnectRef = useRef(true)
  const messagesEndRef = useRef(null)
  const listRef = useRef(null)
  const contentRef = useRef('')
  const sendingRef = useRef(false)

  const apiBase = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000')
    .replace(/\/+$/, '')

  const historyUrl = `/api/workspaces/${workspaceId}/messages`

  const addMessage = useCallback((message) => {
    setMessages((current) => mergeMessages(current, [message]))
  }, [])

  useEffect(() => {
    contentRef.current = content
  }, [content])

  const loadHistory = useCallback(async () => {
    if (!workspaceId) return

    try {
      const response = await api.get(historyUrl, {
        params: { limit: 50 },
      })

      setMessages((current) =>
        mergeMessages(current, response.data.messages || []),
      )
      setError('')
    } catch (err) {
      setError(`Could not load chat history: ${getErrorMessage(err)}`)
    } finally {
      setLoading(false)
    }
  }, [historyUrl, workspaceId])

  useEffect(() => {
    if (!workspaceId) return

    let disposed = false
    let socket = null
    let pollInterval = null

    shouldReconnectRef.current = true
    reconnectAttemptsRef.current = 0
    setMessages([])
    setLoading(true)
    setError('')
    setConnection('connecting')

    const wsBase = apiBase.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:')
    const socketUrl = `${wsBase}/api/ws/workspaces/${workspaceId}/chat`

    function connect() {
      if (disposed || !shouldReconnectRef.current) return

      setConnection(reconnectAttemptsRef.current > 0 ? 'reconnecting' : 'connecting')

      // Null-out the old socket's handlers so a stale socket can't fire events
      if (socket) {
        socket.onopen = null
        socket.onmessage = null
        socket.onerror = null
        socket.onclose = null
      }

      try {
        socket = new WebSocket(socketUrl)
        socketRef.current = socket
      } catch {
        scheduleReconnect()
        return
      }

      socket.onopen = () => {
        reconnectAttemptsRef.current = 0
        setConnection('connected')
        setError('')
        // Re-fetch history on every (re)connect to catch messages missed during disconnect
        loadHistory()
      }

      socket.onmessage = (event) => {
        console.log('[CHAT] WebSocket event received:', event.data)
        let payload

        try {
          payload = JSON.parse(event.data)
        } catch {
          return
        }

        if (payload.type === 'connected') {
          return
        }

        if (payload.type === 'ping') {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'pong' }))
          }
          return
        }

        if (payload.type === 'message' && payload.message) {
          const incoming = payload.message

          setMessages((current) => {
            const withoutPending = incoming.client_message_id
              ? current.filter(
                  (message) =>
                    message.client_message_id !== incoming.client_message_id ||
                    message.id === incoming.id,
                )
              : current

            return mergeMessages(withoutPending, [incoming])
          })

          return
        }

        if (payload.type === 'error') {
          setError(payload.message || 'The server rejected the message.')
        }
      }

      socket.onerror = () => {
        setConnection('disconnected')
      }

      socket.onclose = (event) => {
        if (disposed) return

        setConnection('disconnected')

        if (event.code === 1008) {
          setError('Chat access was denied. Please sign in again or check workspace membership.')
          shouldReconnectRef.current = false
          return
        }

        scheduleReconnect()
      }
    }

    function scheduleReconnect() {
      if (disposed || !shouldReconnectRef.current) return

      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
      }

      reconnectAttemptsRef.current += 1
      const delay = Math.min(
        1000 * 2 ** Math.min(reconnectAttemptsRef.current - 1, 5),
        30000,
      )

      reconnectTimerRef.current = setTimeout(() => {
        if (!disposed) connect()
      }, delay)
    }

    // Initial load + connect
    loadHistory()
    connect()

    // Safety-net poll: only re-fetch when disconnected so missed messages
    // appear once the user reconnects. Runs every 60s as a last resort.
    pollInterval = setInterval(() => {
      if (!disposed && socketRef.current?.readyState !== WebSocket.OPEN) {
        loadHistory()
      }
    }, 60000)

    return () => {
      disposed = true
      shouldReconnectRef.current = false

      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
      }

      if (pollInterval) {
        clearInterval(pollInterval)
      }

      if (socket) {
        socket.onclose = null
        socket.close()
      }

      if (socketRef.current === socket) {
        socketRef.current = null
      }
    }
  }, [workspaceId, apiBase, loadHistory])

  useEffect(() => {
    const container = listRef.current
    if (!container) return

    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight

    if (distanceFromBottom < 120) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      setShowScrollButton(false)
    } else {
      setShowScrollButton(true)
    }
  }, [messages])

  async function handleSend(event) {
    event.preventDefault()

    const text = contentRef.current.trim()
    const socket = socketRef.current

    if (!text || sendingRef.current) return

    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setError('Chat is reconnecting. Please try again when connected.')
      return
    }

    const clientMessageId = crypto.randomUUID()
    const now = new Date().toISOString()

    const optimisticMessage = {
      id: `pending-${clientMessageId}`,
      client_message_id: clientMessageId,
      workspace_id: workspaceId,
      sender_id: user?.id,
      sender_name: user?.name || user?.username || 'You',
      sender_picture: user?.picture || null,
      content: text,
      created_at: now,
      pending: true,
    }

    // Render immediately, without waiting for MongoDB.
    setMessages((current) => mergeMessages(current, [optimisticMessage]))

    sendingRef.current = true
    setSending(true)
    setError('')
    setContent('')
    contentRef.current = ''

    try {
      socket.send(
        JSON.stringify({
          type: 'send_message',
          content: text,
          client_message_id: clientMessageId,
        }),
      )
    } catch {
      setError('Could not send the message. Please try again.')

      setMessages((current) =>
        current.filter((message) => message.id !== optimisticMessage.id),
      )

      setContent(text)
      contentRef.current = text
    } finally {
      sendingRef.current = false
      setSending(false)
    }
  }

  const connectionLabel = {
    connected: 'Connected',
    connecting: 'Connecting',
    reconnecting: 'Reconnecting',
    disconnected: 'Disconnected',
  }[connection]

  const isConnected = connection === 'connected'

  return (
    <div className="absolute inset-0 flex h-full min-h-0 flex-col overflow-hidden bg-[#F8F8F6] text-[#18181B]">
      <header className="flex shrink-0 items-center justify-between border-b border-[#E4E4E0] bg-white px-4 py-3 sm:px-6">
        <div>
          <h2 className="text-sm font-bold sm:text-base">Team Chat</h2>
          <p className="mt-0.5 text-[11px] text-[#71717A]">
            Messages are shared with workspace members.
          </p>
        </div>

        <div className="flex items-center gap-1.5 rounded-full border border-[#E4E4E0] bg-[#F8F8F6] px-2.5 py-1.5">
          {isConnected ? (
            <Wifi className="h-3.5 w-3.5 text-green-700" />
          ) : connection === 'connecting' || connection === 'reconnecting' ? (
            <LoaderCircle className="h-3.5 w-3.5 animate-spin text-amber-700" />
          ) : (
            <WifiOff className="h-3.5 w-3.5 text-red-600" />
          )}
          <span className="text-[10px] font-semibold">{connectionLabel}</span>
        </div>
      </header>

      {error && (
        <div className="flex shrink-0 items-start gap-2 border-b border-red-200 bg-red-50 px-4 py-2.5 text-xs text-red-800">
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
          <button
            type="button"
            onClick={() => setError('')}
            className="ml-auto font-semibold"
          >
            Dismiss
          </button>
        </div>
      )}

      <main
        ref={listRef}
        onScroll={(event) => {
          const element = event.currentTarget
          setShowScrollButton(
            element.scrollHeight - element.scrollTop - element.clientHeight > 120,
          )
        }}
        className="relative flex-1 space-y-4 overflow-y-auto px-4 py-5 sm:px-8 sm:py-6"
      >
        {loading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((item) => (
              <div key={item} className="max-w-[70%] animate-pulse">
                <div className="mb-2 h-3 w-24 rounded bg-[#E4E4E0]" />
                <div className="h-12 rounded-xl border border-[#E4E4E0] bg-white" />
              </div>
            ))}
          </div>
        ) : messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl border border-[#E4E4E0] bg-white">
              <Send className="h-5 w-5" />
            </div>
            <h3 className="text-base font-bold">Start the conversation</h3>
            <p className="mt-1 max-w-xs text-xs leading-relaxed text-[#71717A]">
              Send a message to your teammates. New messages will appear here instantly.
            </p>
          </div>
        ) : (
          messages.map((message) => {
            const isMe = message.sender_id === user?.id
            const senderName = isMe ? 'You' : message.sender_name

            return (
              <article
                key={message.id}
                className={`flex flex-col ${isMe ? 'items-end' : 'items-start'}`}
              >
                <div className="mb-1.5 flex items-center gap-2 px-1 text-[11px] text-[#71717A]">
                  <span className="font-semibold text-[#18181B]">{senderName}</span>
                  <span>·</span>
                  <time dateTime={message.created_at}>
                    {formatTime(message.created_at)}
                  </time>
                </div>

                <div
                  className={`max-w-[88%] whitespace-pre-wrap break-words rounded-2xl px-4 py-2.5 text-sm leading-relaxed sm:max-w-[70%] ${isMe
                      ? 'rounded-tr-sm bg-[#18181B] text-white'
                      : 'rounded-tl-sm border border-[#E4E4E0] bg-white text-[#18181B]'
                    }`}
                >
                  {message.content}
                </div>
              </article>
            )
          })
        )}

        <div ref={messagesEndRef} />
      </main>

      {showScrollButton && (
        <button
          type="button"
          onClick={() => {
            messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
            setShowScrollButton(false)
          }}
          className="absolute bottom-24 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-full bg-[#18181B] px-3.5 py-2 text-xs font-semibold text-white shadow-lg"
        >
          <ArrowDown className="h-3.5 w-3.5" />
          Latest messages
        </button>
      )}

      <form
        onSubmit={handleSend}
        className="flex shrink-0 items-center gap-2 border-t border-[#E4E4E0] bg-white p-3 sm:p-4"
      >
        <input
          type="text"
          value={content}
          onChange={(event) => setContent(event.target.value)}
          maxLength={5000}
          placeholder="Message your teammates..."
          aria-label="Message your teammates"
          className="min-w-0 flex-1 rounded-xl border border-[#E4E4E0] bg-[#F8F8F6] px-4 py-3 text-sm outline-none transition focus:border-[#18181B] focus:ring-2 focus:ring-black/10"
        />

        <button
          type="submit"
          disabled={!content.trim() || sending || !isConnected}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#18181B] text-white transition hover:bg-[#27272A] disabled:cursor-not-allowed disabled:opacity-40"
          aria-label="Send message"
          title="Send message"
        >
          {sending ? (
            <LoaderCircle className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </button>
      </form>
    </div>
  )
}
