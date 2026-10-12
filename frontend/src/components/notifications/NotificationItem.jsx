import React, { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Check, X, Clock, User } from 'lucide-react'

// Curated avatar background hues matching screenshot aesthetic
const AVATAR_COLORS = [
  'bg-sky-100 text-sky-800 border-sky-200',
  'bg-amber-100 text-amber-900 border-amber-200',
  'bg-rose-100 text-rose-800 border-rose-200',
  'bg-orange-100 text-orange-900 border-orange-200',
  'bg-emerald-100 text-emerald-800 border-emerald-200',
]

const getAvatarColor = (name = '') => {
  const code = name.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0)
  return AVATAR_COLORS[code % AVATAR_COLORS.length]
}

const formatRelativeTime = (isoString) => {
  try {
    if (!isoString) return 'just now'
    return formatDistanceToNow(new Date(isoString), { addSuffix: true })
      .replace(/^about /, '')
      .replace(/^less than a minute ago/, 'just now')
  } catch {
    return 'recently'
  }
}

const NotificationItem = ({
  notification,
  onItemClick,
  onAccept,
  onReject,
  onDecline,
  actionLoading = false,
}) => {
  const [imgError, setImgError] = useState(false)
  const isInvitation = notification.type === 'invitation'
  const isPending = notification.status === 'pending'
  const avatarClass = getAvatarColor(notification.actor?.name || 'User')

  const handleContainerClick = (e) => {
    // If user clicked directly on action buttons, do not trigger container navigation
    if (e.target.closest('button')) return
    if (onItemClick) {
      onItemClick(notification)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      handleContainerClick(e)
    }
  }

  const handleRejectClick = (e) => {
    e.stopPropagation()
    if (onReject) {
      onReject(notification)
    } else if (onDecline) {
      onDecline(notification)
    }
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={handleContainerClick}
      onKeyDown={handleKeyDown}
      className={`relative w-full p-3.5 sm:p-4 text-left transition-colors duration-150 cursor-pointer focus:outline-none focus-visible:bg-[#F4F4F2] ${
        notification.isRead
          ? 'bg-white hover:bg-[#F9F9F8]'
          : 'bg-[#FCFCFB] hover:bg-[#F5F5F3]'
      }`}
    >
      <div className="flex items-start space-x-3.5">
        {/* Left: Avatar with Status Dot */}
        <div className="relative shrink-0">
          {notification.actor?.avatar && !imgError ? (
            <img
              src={notification.actor.avatar}
              alt={notification.actor.name}
              onError={() => setImgError(true)}
              className="w-9 h-9 rounded-full object-cover border border-[#E4E4E0] shadow-2xs"
            />
          ) : (
            <div
              className={`w-9 h-9 rounded-full flex items-center justify-center font-display font-bold text-xs border shadow-2xs ${avatarClass}`}
            >
              {notification.actor?.initials || <User className="w-4 h-4" />}
            </div>
          )}

          {/* Green online indicator dot */}
          <span
            className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 bg-[#22C55E] border-2 border-white rounded-full ring-1 ring-black/5"
            aria-hidden="true"
          />
        </div>

        {/* Center: Notification Content */}
        <div className="flex-1 min-w-0 pr-2">
          <p className="text-xs sm:text-sm text-[#18181B] leading-snug break-words">
            <span className="font-semibold text-[#18181B]">
              {notification.actor?.name}
            </span>{' '}
            <span className="text-[#52525B]">
              {notification.actionText || 'invited you to join'}
            </span>{' '}
            <span className="font-bold text-[#18181B]">
              {notification.targetName || notification.workspaceName || notification.title}
            </span>
          </p>

          {/* Subtitle: Time • Context/Workspace */}
          <div className="flex items-center space-x-1.5 text-[11px] sm:text-xs text-[#71717A] mt-1">
            <span>{formatRelativeTime(notification.createdAt)}</span>
            {notification.workspaceName && (
              <>
                <span>•</span>
                <span className="truncate max-w-[200px] font-medium text-[#52525B]">
                  {notification.workspaceName}
                </span>
              </>
            )}
          </div>

          {/* Invitation Actions: Reject and Accept Buttons */}
          {isInvitation && isPending && (
            <div className="flex items-center space-x-2 mt-3 pt-1">
              <button
                type="button"
                onClick={handleRejectClick}
                disabled={actionLoading}
                className="px-3.5 py-1 text-xs font-semibold text-[#18181B] bg-white border border-[#E4E4E0] rounded-xl hover:bg-[#F4F4F5] hover:border-[#D4D4D0] active:scale-97 disabled:opacity-50 transition-all cursor-pointer shadow-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-[#18181B]"
              >
                Reject
              </button>

              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  onAccept?.(notification)
                }}
                disabled={actionLoading}
                className="px-3.5 py-1 text-xs font-semibold text-white bg-[#C2410C] hover:bg-[#9A3412] active:scale-97 rounded-xl shadow-xs disabled:opacity-50 transition-all cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C2410C]"
              >
                {actionLoading ? 'Updating...' : 'Accept'}
              </button>
            </div>
          )}

          {/* Feedback for accepted / rejected invitations */}
          {isInvitation && !isPending && (
            <div className="mt-2.5">
              {notification.status === 'accepted' && (
                <span className="inline-flex items-center space-x-1 text-[11px] font-semibold text-[#15803D] bg-[#F0FDF4] border border-[#DCFCE7] px-2 py-0.5 rounded-md">
                  <Check className="w-3 h-3" />
                  <span>Invitation accepted</span>
                </span>
              )}
              {(notification.status === 'declined' || notification.status === 'rejected') && (
                <span className="inline-flex items-center space-x-1 text-[11px] font-semibold text-[#71717A] bg-[#F4F4F5] border border-[#E4E4E0] px-2 py-0.5 rounded-md">
                  <X className="w-3 h-3" />
                  <span>Invitation rejected</span>
                </span>
              )}
              {notification.status === 'expired' && (
                <span className="inline-flex items-center space-x-1 text-[11px] font-semibold text-[#DC2626] bg-[#FEF2F2] border border-[#FEE2E2] px-2 py-0.5 rounded-md">
                  <Clock className="w-3 h-3" />
                  <span>Invitation expired</span>
                </span>
              )}
            </div>
          )}
        </div>

        {/* Right: Unread Purple Dot Indicator */}
        <div className="shrink-0 flex items-center justify-center pt-1.5">
          {!notification.isRead && (
            <span
              className="w-2 h-2 rounded-full bg-[#C2410C] shadow-xs"
              title="Unread notification"
              aria-label="Unread"
            />
          )}
        </div>
      </div>
    </div>
  )
}

export default NotificationItem
