import React, { forwardRef } from 'react'
import { Bell } from 'lucide-react'

const NotificationBell = forwardRef(
  ({ isOpen, unreadCount = 0, onClick, onKeyDown, className = '' }, ref) => {
    const formattedCount = unreadCount > 99 ? '99+' : unreadCount
    const hasUnread = unreadCount > 0

    return (
      <button
        ref={ref}
        type="button"
        onClick={onClick}
        onKeyDown={onKeyDown}
        aria-label={
          hasUnread
            ? `Notifications, ${unreadCount} unread notifications`
            : 'Notifications'
        }
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        title="Notifications"
        className={`relative p-2 sm:p-2.5 rounded-xl border transition-all duration-150 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#18181B] focus-visible:ring-offset-2 ${
          isOpen
            ? 'bg-[#18181B] text-white border-[#18181B] shadow-sm'
            : 'bg-white hover:bg-[#F4F4F2] text-[#18181B] border-[#E4E4E0] shadow-2xs hover:border-[#D4D4D0]'
        } ${className}`}
      >
        <Bell className="w-4 h-4 sm:w-[18px] sm:h-[18px] transition-transform group-hover:scale-105" />

        {/* Small badge with unread notifications count */}
        {hasUnread && (
          <span
            className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 bg-[#C2410C] text-white text-[10px] font-extrabold font-mono rounded-full flex items-center justify-center shadow-xs border-2 border-white animate-in zoom-in duration-200"
            aria-hidden="true"
          >
            {formattedCount}
          </span>
        )}
      </button>
    )
  }
)

NotificationBell.displayName = 'NotificationBell'

export default NotificationBell
