import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  ArrowLeft,
  CheckCheck,
  Inbox,
  Bell,
  RefreshCw,
} from 'lucide-react'
import NotificationItem from '../components/notifications/NotificationItem'
import {
  getNotifications,
  markAsRead,
  markAllAsRead,
  acceptInvitation,
  declineInvitation,
} from '../api/notifications'
import { INITIAL_WORKSPACE_INVITATIONS } from '../api/fixtures/notificationFixtures'

const Notifications = () => {
  const navigate = useNavigate()
  const [notifications, setNotifications] = useState(INITIAL_WORKSPACE_INVITATIONS)
  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [markingAll, setMarkingAll] = useState(false)
  const [feedback, setFeedback] = useState(null)

  const showFeedback = (msg, type = 'success') => {
    setFeedback({ msg, type })
    setTimeout(() => setFeedback(null), 3000)
  }

  const loadNotifications = useCallback(async () => {
    try {
      const data = await getNotifications({ tab: 'inbox' })
      if (Array.isArray(data?.notifications)) {
        setNotifications(data.notifications)
      }
    } catch {
      // Backend unavailable; keep dummy invitations
    }
  }, [])

  useEffect(() => {
    loadNotifications()
  }, [loadNotifications])

  const unreadCount = notifications.filter((n) => !n.isRead).length

  const handleMarkAllAsRead = async () => {
    if (unreadCount === 0 || markingAll) return
    setMarkingAll(true)
    setNotifications((prev) => prev.map((n) => ({ ...n, isRead: true })))

    try {
      await markAllAsRead()
    } catch {
      // Backend pending
    } finally {
      setMarkingAll(false)
      showFeedback('All notifications marked as read')
    }
  }

  const handleItemClick = async (item) => {
    if (!item.isRead) {
      setNotifications((prev) =>
        prev.map((n) => (n.id === item.id ? { ...n, isRead: true } : n))
      )
      try {
        await markAsRead(item.id)
      } catch {
        // Backend pending
      }
    }

    if (item.workspaceId) {
      navigate(`/w/${item.workspaceId}/chat`)
    }
  }

  const handleAccept = async (item) => {
    const invId = item.invitationId || item.id
    setActionLoading(true)
    setNotifications((prev) =>
      prev.map((n) =>
        n.id === item.id ? { ...n, status: 'accepted', isRead: true } : n
      )
    )
    try {
      await acceptInvitation(invId)
      window.dispatchEvent(new CustomEvent('workspaces:updated'))
    } catch {
      // Backend pending
    } finally {
      setActionLoading(false)
      showFeedback(`Accepted invitation to ${item.workspaceName || 'workspace'}`)
    }
  }

  const handleReject = async (item) => {
    const invId = item.invitationId || item.id
    setActionLoading(true)
    setNotifications((prev) =>
      prev.map((n) =>
        n.id === item.id ? { ...n, status: 'rejected', isRead: true } : n
      )
    )
    try {
      await declineInvitation(invId)
    } catch {
      // Backend pending
    } finally {
      setActionLoading(false)
      showFeedback(`Rejected invitation to ${item.workspaceName || 'workspace'}`)
    }
  }

  return (
    <div className="min-h-screen w-full bg-[#F8F8F6] text-[#18181B] p-4 sm:p-8 lg:p-10 font-sans overflow-y-auto selection:bg-zinc-200 selection:text-zinc-900">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Navigation Breadcrumb & Back */}
        <div className="flex items-center justify-between">
          <Link
            to="/workspaces"
            className="inline-flex items-center space-x-1.5 text-xs font-semibold text-[#71717A] hover:text-[#18181B] transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Back to Workspaces</span>
          </Link>

          {feedback && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="text-xs px-3 py-1 rounded-xl font-semibold border bg-[#18181B] text-white border-[#27272A]"
            >
              {feedback.msg}
            </motion.div>
          )}
        </div>

        {/* Page Header */}
        <div className="bg-white border border-[#E4E4E0] rounded-2xl p-5 sm:p-7 shadow-xs flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center space-x-3.5">
            <div className="w-11 h-11 rounded-xl bg-[#18181B] text-white flex items-center justify-center shrink-0 shadow-xs">
              <Bell className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="font-display font-bold text-xl sm:text-2xl text-[#18181B] tracking-tight">
                  Inbox Notifications
                </h1>
                {unreadCount > 0 && (
                  <span className="text-xs font-mono font-bold px-2.5 py-0.5 rounded-full bg-[#C2410C] text-white">
                    {unreadCount} unread
                  </span>
                )}
              </div>
              <p className="text-[#52525B] text-xs mt-1">
                Workspace invitations and collaboration requests
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={handleMarkAllAsRead}
              disabled={unreadCount === 0 || markingAll || loading}
              className="btn-secondary text-xs px-4 py-2 flex items-center space-x-1.5 cursor-pointer disabled:opacity-50"
            >
              <CheckCheck className="w-4 h-4 text-[#71717A]" />
              <span>{markingAll ? 'Marking...' : 'Mark all as read'}</span>
            </button>
          </div>
        </div>

        {/* Notification List Container */}
        <div className="bg-white border border-[#E4E4E0] rounded-2xl shadow-xs overflow-hidden">
          {notifications.length === 0 ? (
            /* Clean Empty State */
            <div className="p-12 text-center space-y-3">
              <div className="w-12 h-12 rounded-2xl bg-[#F8F8F6] text-[#71717A] border border-[#E4E4E0] mx-auto flex items-center justify-center">
                <Inbox className="w-6 h-6" />
              </div>
              <h3 className="font-display font-bold text-base text-[#18181B]">
                Your inbox is empty
              </h3>
              <p className="text-xs text-[#71717A] max-w-sm mx-auto leading-relaxed">
                You have no pending workspace invitations right now.
              </p>
            </div>
          ) : (
            /* Card/Row list */
            <div className="divide-y divide-[#F4F4F2]">
              {notifications.map((item) => (
                <NotificationItem
                  key={item.id}
                  notification={item}
                  onItemClick={handleItemClick}
                  onAccept={handleAccept}
                  onReject={handleReject}
                  actionLoading={actionLoading}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default Notifications
