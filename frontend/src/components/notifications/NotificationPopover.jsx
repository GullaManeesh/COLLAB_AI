import React, { useRef, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { 
  X, 
  ArrowRight, 
  Inbox, 
  AlertCircle, 
  RefreshCw,
  Bell
} from 'lucide-react'
import NotificationItem from './NotificationItem'

const NotificationPopover = ({
  isOpen,
  onClose,
  notifications = [],
  unreadCount = 0,
  loading = false,
  error = null,
  onRetry,
  onMarkAllAsRead,
  onItemClick,
  onAcceptInvitation,
  onRejectInvitation,
  actionLoading = false,
  markingAll = false,
}) => {
  const popoverRef = useRef(null)

  // Handle Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose?.()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  return (
    <motion.div
      ref={popoverRef}
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 8, scale: 0.98 }}
      transition={{ duration: 0.16, ease: 'easeOut' }}
      onClick={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="false"
      aria-label="Notification center"
      className="absolute right-0 top-full mt-3 w-[calc(100vw-2rem)] sm:w-[420px] bg-white rounded-2xl border border-[#E4E4E0] shadow-xl z-50 overflow-hidden flex flex-col select-none"
    >
      {/* Top arrow caret pointing to bell */}
      <div 
        className="absolute -top-2 right-4 w-3.5 h-3.5 bg-white border-t border-l border-[#E4E4E0] rotate-45 z-10" 
        aria-hidden="true" 
      />

      {/* Header */}
      <div className="p-4 sm:p-4.5 pb-3 border-b border-[#F4F4F2] flex items-center justify-between bg-white relative z-20">
        <div className="flex items-center space-x-2">
          <h2 className="font-display font-bold text-base text-[#18181B] tracking-tight">
            Notifications
          </h2>
          {unreadCount > 0 && (
            <span className="text-[11px] font-mono font-bold px-2 py-0.5 rounded-full bg-[#F4F4F5] text-[#52525B] border border-[#E4E4E0]">
              {unreadCount} unread
            </span>
          )}
        </div>

        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={onMarkAllAsRead}
            disabled={unreadCount === 0 || markingAll || loading}
            className="text-xs font-semibold text-[#71717A] hover:text-[#18181B] disabled:opacity-40 disabled:hover:text-[#71717A] transition-colors cursor-pointer focus:outline-none focus-visible:underline"
          >
            {markingAll ? 'Marking...' : 'Mark all as read'}
          </button>

          {/* Close button for small mobile screens */}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close notifications"
            className="sm:hidden p-1 text-[#71717A] hover:text-[#18181B] rounded-lg hover:bg-[#F4F4F2]"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Inbox Tab Navigation (clean, single Inbox tab) */}
      <div className="px-4 pt-2.5 pb-2 border-b border-[#F4F4F2] flex items-center justify-between bg-white relative z-20">
        <div className="flex items-center space-x-2">
          <div className="relative pb-1.5 text-xs font-bold text-[#18181B] flex items-center space-x-1.5">
            <span>Inbox</span>
            {unreadCount > 0 && (
              <span className="min-w-[18px] h-[18px] px-1 rounded-full bg-[#18181B] text-white text-[10px] font-mono flex items-center justify-center font-bold">
                {unreadCount}
              </span>
            )}
            <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-[#18181B] rounded-full" />
          </div>
        </div>

        <span className="text-[11px] text-[#71717A] font-medium pb-1.5">
          Workspace Invitations
        </span>
      </div>

      {/* Scrollable list */}
      <div className="max-h-[380px] overflow-y-auto divide-y divide-[#F4F4F2] bg-white">
        {loading ? (
          /* Skeleton Loading state */
          <div className="p-4 space-y-4 animate-pulse">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex items-start space-x-3.5">
                <div className="w-9 h-9 rounded-full bg-[#E4E4E0] shrink-0" />
                <div className="flex-1 space-y-2">
                  <div className="h-3.5 bg-[#E4E4E0] rounded w-5/6" />
                  <div className="h-2.5 bg-[#F4F4F2] rounded w-1/2" />
                </div>
              </div>
            ))}
          </div>
        ) : error ? (
          /* Error State */
          <div className="p-6 text-center space-y-3">
            <div className="w-10 h-10 rounded-full bg-[#FEF2F2] text-[#DC2626] mx-auto flex items-center justify-center">
              <AlertCircle className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs font-bold text-[#18181B]">
                Unable to load notifications
              </p>
              <p className="text-[11px] text-[#71717A] mt-1 max-w-xs mx-auto leading-relaxed">
                {error.message || 'Notification service error.'}
              </p>
            </div>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="btn-secondary text-xs px-3 py-1.5 inline-flex items-center space-x-1"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Retry</span>
              </button>
            )}
          </div>
        ) : notifications.length === 0 ? (
          /* Empty State */
          <div className="p-8 text-center space-y-2.5">
            <div className="w-10 h-10 rounded-2xl bg-[#F8F8F6] text-[#71717A] border border-[#E4E4E0] mx-auto flex items-center justify-center">
              <Inbox className="w-5 h-5" />
            </div>
            <p className="text-xs font-bold text-[#18181B]">Inbox is empty</p>
            <p className="text-[11px] text-[#71717A] max-w-xs mx-auto">
              You're all caught up! No active workspace invitations in your inbox.
            </p>
          </div>
        ) : (
          /* Invitations list */
          notifications.map((item) => (
            <NotificationItem
              key={item.id}
              notification={item}
              onItemClick={onItemClick}
              onAccept={onAcceptInvitation}
              onReject={onRejectInvitation}
              actionLoading={actionLoading}
            />
          ))
        )}
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-[#E4E4E0] bg-[#F8F8F6] flex items-center justify-center">
        <Link
          to="/notifications"
          onClick={onClose}
          className="text-xs font-semibold text-[#18181B] hover:text-[#52525B] flex items-center space-x-1 transition-colors group cursor-pointer"
        >
          <span>View all notifications</span>
          <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
        </Link>
      </div>
    </motion.div>
  )
}

export default NotificationPopover
