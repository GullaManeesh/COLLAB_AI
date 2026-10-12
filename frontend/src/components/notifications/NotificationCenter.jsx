import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import NotificationBell from './NotificationBell'
import NotificationPopover from './NotificationPopover'
import {
  getNotifications,
  getUnreadCount,
  markAsRead,
  markAllAsRead,
  acceptInvitation,
  declineInvitation,
} from '../../api/notifications'
import { INITIAL_WORKSPACE_INVITATIONS } from '../../api/fixtures/notificationFixtures'

const NotificationCenter = ({ className = '', onWorkspaceChange }) => {
  const navigate = useNavigate()
  const containerRef = useRef(null)
  const bellRef = useRef(null)

  const [isOpen, setIsOpen] = useState(false)
  // Default to dummy workspace invitations
  const [notifications, setNotifications] = useState(INITIAL_WORKSPACE_INVITATIONS)
  const [unreadCount, setUnreadCount] = useState(
    INITIAL_WORKSPACE_INVITATIONS.filter((n) => !n.isRead).length
  )
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [markingAll, setMarkingAll] = useState(false)
  const [feedback, setFeedback] = useState(null)

  // Show transient feedback message
  const showFeedback = useCallback((msg, type = 'success') => {
    setFeedback({ msg, type })
    const timer = setTimeout(() => setFeedback(null), 3000)
    return () => clearTimeout(timer)
  }, [])

  // Attempt to sync with backend if available; otherwise gracefully keep dummy invitations
  const loadNotifications = useCallback(async () => {
    try {
      const data = await getNotifications({ tab: 'inbox' })
      if (Array.isArray(data?.notifications)) {
        setNotifications(data.notifications)
        setUnreadCount(
          data.unreadCount ?? data.notifications.filter((n) => !n.isRead).length
        )
      }
    } catch {
      // Backend unavailable: keep dummy invitations
    }
  }, [])

  useEffect(() => {
    loadNotifications()
  }, [loadNotifications])

  // Click outside listener
  useEffect(() => {
    const handlePointerDown = (event) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target) &&
        bellRef.current &&
        !bellRef.current.contains(event.target)
      ) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('pointerdown', handlePointerDown)
    }
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
    }
  }, [isOpen])

  // Toggle popover
  const toggleOpen = () => {
    setIsOpen((prev) => !prev)
  }

  // Handle Mark All as Read
  const handleMarkAllAsRead = async () => {
    if (unreadCount === 0 || markingAll) return
    setMarkingAll(true)

    // Update frontend state
    setNotifications((prev) => prev.map((n) => ({ ...n, isRead: true })))
    setUnreadCount(0)

    try {
      await markAllAsRead()
    } catch {
      // Backend pending; frontend state is already updated
    } finally {
      setMarkingAll(false)
      showFeedback('All notifications marked as read')
    }
  }

  // Handle Item Click (Mark as read & optionally navigate to workspace)
  const handleItemClick = async (item) => {
    if (!item.isRead) {
      setNotifications((prev) =>
        prev.map((n) => (n.id === item.id ? { ...n, isRead: true } : n))
      )
      setUnreadCount((c) => Math.max(0, c - 1))
      try {
        await markAsRead(item.id)
      } catch {
        // Backend pending
      }
    }

    if (item.workspaceId) {
      setIsOpen(false)
      navigate(`/w/${item.workspaceId}/chat`)
    }
  }

  // Handle Accept Invitation
  const handleAcceptInvitation = async (item) => {
    const invId = item.invitationId || item.id
    setActionLoading(true)

    // Immediate frontend update
    setNotifications((prev) =>
      prev.map((n) =>
        n.id === item.id ? { ...n, status: 'accepted', isRead: true } : n
      )
    )
    setUnreadCount((c) => (item.isRead ? c : Math.max(0, c - 1)))

    try {
      await acceptInvitation(invId)
      onWorkspaceChange?.()
      window.dispatchEvent(new CustomEvent('workspaces:updated'))
    } catch {
      // Backend pending; UI is already updated
    } finally {
      setActionLoading(false)
      showFeedback(`Accepted invitation to ${item.workspaceName || 'workspace'}`)
    }
  }

  // Handle Reject Invitation
  const handleRejectInvitation = async (item) => {
    const invId = item.invitationId || item.id
    setActionLoading(true)

    // Immediate frontend update
    setNotifications((prev) =>
      prev.map((n) =>
        n.id === item.id ? { ...n, status: 'rejected', isRead: true } : n
      )
    )
    setUnreadCount((c) => (item.isRead ? c : Math.max(0, c - 1)))

    try {
      await declineInvitation(invId)
    } catch {
      // Backend pending; UI is already updated
    } finally {
      setActionLoading(false)
      showFeedback(`Rejected invitation to ${item.workspaceName || 'workspace'}`)
    }
  }

  return (
    <div className={`relative inline-block text-left ${className}`} ref={containerRef}>
      {/* Notification Bell Icon */}
      <NotificationBell
        ref={bellRef}
        isOpen={isOpen}
        unreadCount={unreadCount}
        onClick={toggleOpen}
      />

      {/* Popover */}
      <AnimatePresence>
        {isOpen && (
          <NotificationPopover
            isOpen={isOpen}
            onClose={() => setIsOpen(false)}
            notifications={notifications}
            unreadCount={unreadCount}
            loading={loading}
            error={error}
            onRetry={loadNotifications}
            onMarkAllAsRead={handleMarkAllAsRead}
            onItemClick={handleItemClick}
            onAcceptInvitation={handleAcceptInvitation}
            onRejectInvitation={handleRejectInvitation}
            actionLoading={actionLoading}
            markingAll={markingAll}
          />
        )}
      </AnimatePresence>

      {/* Feedback Toast */}
      {feedback && (
        <div
          role="status"
          className="absolute top-full mt-2 right-0 z-50 px-3 py-1.5 rounded-xl text-xs font-semibold shadow-lg border animate-in fade-in slide-in-from-top-1 bg-[#18181B] text-white border-[#27272A]"
        >
          {feedback.msg}
        </div>
      )}
    </div>
  )
}

export default NotificationCenter
