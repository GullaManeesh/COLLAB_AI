import api from './client'

/**
 * Normalizes notification data from the backend to a standard frontend shape.
 * Handles both camelCase and snake_case API payloads gracefully.
 */
export const normalizeNotification = (item = {}) => {
  return {
    id: item.id || item._id || String(Math.random()),
    type: item.type || (item.invitation_id || item.invitationId ? 'invitation' : 'general'),
    title: item.title || '',
    message: item.message || '',
    actor: {
      name: item.actor?.name || item.actor_name || item.sender_name || 'Team member',
      avatar: item.actor?.avatar || item.actor_avatar || null,
      email: item.actor?.email || item.actor_email || null,
      initials: (item.actor?.name || item.actor_name || 'TM')
        .split(' ')
        .map((n) => n[0])
        .join('')
        .slice(0, 2)
        .toUpperCase(),
    },
    actionText: item.action_text || item.actionText || 'updated',
    targetName: item.target_name || item.targetName || item.workspace_name || item.workspaceName || '',
    workspaceId: item.workspace_id || item.workspaceId || null,
    workspaceName: item.workspace_name || item.workspaceName || 'CollabAI Workspace',
    invitationId: item.invitation_id || item.invitationId || (item.type === 'invitation' ? item.id : null),
    createdAt: item.created_at || item.createdAt || new Date().toISOString(),
    readAt: item.read_at || item.readAt || null,
    isRead: Boolean(item.is_read ?? item.isRead ?? false),
    isArchived: Boolean(item.is_archived ?? item.isArchived ?? false),
    status: item.status || (item.invitation_id || item.invitationId ? 'pending' : 'active'), // 'pending' | 'accepted' | 'declined' | 'expired'
  }
}

/**
 * Retrieve notifications with optional tab filtering and pagination.
 * Proposed backend endpoint: GET /api/notifications?tab={tab}&page={page}&limit={limit}
 */
export const getNotifications = async ({ tab = 'inbox', page = 1, limit = 20 } = {}) => {
  const response = await api.get('/api/notifications', {
    params: { tab, page, limit },
  })
  const items = Array.isArray(response.data)
    ? response.data
    : response.data?.notifications || response.data?.items || []
  const total = response.data?.total ?? items.length
  const unreadCount = response.data?.unread_count ?? response.data?.unreadCount ?? 0

  return {
    notifications: items.map(normalizeNotification),
    total,
    unreadCount,
  }
}

/**
 * Retrieve total unread notifications count for badge display.
 * Proposed backend endpoint: GET /api/notifications/unread-count
 */
export const getUnreadCount = async () => {
  const response = await api.get('/api/notifications/unread-count')
  return typeof response.data === 'number'
    ? response.data
    : response.data?.unread_count ?? response.data?.unreadCount ?? response.data?.count ?? 0
}

/**
 * Mark a single notification as read.
 * Proposed backend endpoint: PATCH /api/notifications/:id/read
 */
export const markAsRead = async (notificationId) => {
  const response = await api.patch(`/api/notifications/${notificationId}/read`)
  return response.data
}

/**
 * Mark all active notifications as read.
 * Proposed backend endpoint: POST /api/notifications/mark-all-read
 */
export const markAllAsRead = async () => {
  const response = await api.post('/api/notifications/mark-all-read')
  return response.data
}

/**
 * Accept a pending workspace invitation.
 * Proposed backend endpoint: POST /api/workspaces/invitations/:invitationId/accept
 */
export const acceptInvitation = async (invitationId) => {
  const response = await api.post(`/api/workspaces/invitations/${invitationId}/accept`)
  return response.data
}

/**
 * Decline a pending workspace invitation.
 * Proposed backend endpoint: POST /api/workspaces/invitations/:invitationId/decline
 */
export const declineInvitation = async (invitationId) => {
  const response = await api.post(`/api/workspaces/invitations/${invitationId}/decline`)
  return response.data
}
