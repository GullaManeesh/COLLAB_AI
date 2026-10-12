import React, { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { Users, Clock, Briefcase, Plus, Layers, LogOut, ArrowRight } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import NotificationCenter from '../components/notifications/NotificationCenter'
import CreateWorkspaceModal from '../components/workspaces/CreateWorkspaceModal'
import EditWorkspaceModal from '../components/workspaces/EditWorkspaceModal'
import DeleteWorkspaceModal from '../components/workspaces/DeleteWorkspaceModal'
import WorkspaceCardMenu from '../components/workspaces/WorkspaceCardMenu'
import api from '../api/client'

const extractWorkspaceList = (payload) => {
  if (Array.isArray(payload)) {
    return payload
  }
  if (Array.isArray(payload?.workspaces)) {
    return payload.workspaces
  }
  if (Array.isArray(payload?.items)) {
    return payload.items
  }
  return []
}

const getApiErrorMessage = (error) => {
  const status = error?.response?.status
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) {
    return detail.trim()
  }

  if (status === 404) {
    return 'Workspace API endpoint is not available yet.'
  }
  if (status === 400) {
    return 'Please check the form values and try again.'
  }
  if (status === 401) {
    return 'Your session has expired. Please sign in again.'
  }
  if (status === 403) {
    return 'You do not have permission to perform this action.'
  }
  if (status && status >= 500) {
    return 'Workspace service is temporarily unavailable. Please try again.'
  }
  if (error?.code === 'ECONNABORTED') {
    return 'The request timed out. Please try again.'
  }
  return 'Unable to complete request right now. Please try again.'
}

const Workspaces = () => {
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const currentUserId = String(user?.id || user?._id || '')

  const normalizeWorkspace = useCallback((workspace = {}) => {
    const name = typeof workspace.name === 'string' ? workspace.name.trim() : ''
    const description = typeof workspace.description === 'string' ? workspace.description.trim() : ''
    const ownerId = String(workspace.owner_id || workspace.ownerId || '')
    const isOwner = Boolean(
      workspace.role === 'owner' || (ownerId && currentUserId && ownerId === currentUserId)
    )

    return {
      id: String(workspace.id || workspace._id || workspace.workspace_id || workspace.workspaceId || ''),
      name: name || 'Untitled Workspace',
      description: description || 'Collaborative human-agent workspace',
      member_count: Number(workspace.member_count ?? workspace.memberCount ?? 1),
      last_activity_at: workspace.last_activity_at || workspace.lastActivityAt || workspace.updated_at || new Date().toISOString(),
      owner_id: ownerId,
      role: isOwner ? 'owner' : (workspace.role || 'member'),
    }
  }, [currentUserId])

  const [workspaces, setWorkspaces] = useState([])
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingWorkspace, setEditingWorkspace] = useState(null)
  const [deletingWorkspace, setDeletingWorkspace] = useState(null)
  const [submitError, setSubmitError] = useState('')
  const [creating, setCreating] = useState(false)
  const [loadingList, setLoadingList] = useState(true)
  const [toastMessage, setToastMessage] = useState(null)

  const showToast = useCallback((msg) => {
    setToastMessage(msg)
    const timer = setTimeout(() => setToastMessage(null), 3000)
    return () => clearTimeout(timer)
  }, [])

  const openCreateModal = () => {
    setSubmitError('')
    setShowCreateModal(true)
  }

  const closeCreateModal = () => {
    if (creating) return
    setShowCreateModal(false)
    setSubmitError('')
  }

  const refreshWorkspaces = useCallback(async ({ withLoader = false } = {}) => {
    if (withLoader) {
      setLoadingList(true)
    }
    try {
      const response = await api.get('/api/workspaces')
      const items = extractWorkspaceList(response.data)
        .map(normalizeWorkspace)
        .filter((ws) => ws.id)
      setWorkspaces(items)
      return items
    } catch {
      return null
    } finally {
      if (withLoader) {
        setLoadingList(false)
      }
    }
  }, [normalizeWorkspace])

  useEffect(() => {
    refreshWorkspaces({ withLoader: true })

    const handleWorkspacesUpdated = () => {
      refreshWorkspaces()
    }
    window.addEventListener('workspaces:updated', handleWorkspacesUpdated)
    return () => {
      window.removeEventListener('workspaces:updated', handleWorkspacesUpdated)
    }
  }, [refreshWorkspaces])

  const handleCreate = async ({ name, description, invitees }) => {
    if (creating) return

    setSubmitError('')
    setCreating(true)

    try {
      const response = await api.post('/api/workspaces', {
        name,
        description: description || '',
        initial_members: invitees || [],
      })

      const created = normalizeWorkspace(
        response?.data?.workspace || response?.data || {}
      )

      await refreshWorkspaces()

      if (created.id) {
        setWorkspaces((prev) => [
          created,
          ...prev.filter((item) => item.id !== created.id),
        ])
      }

      setShowCreateModal(false)
      setSubmitError('')
      showToast(`Created workspace "${name}"`)
    } catch (error) {
      setSubmitError(getApiErrorMessage(error))
    } finally {
      setCreating(false)
    }
  }

  const handleWorkspaceSaved = (updated) => {
    const normalized = normalizeWorkspace(updated)
    setWorkspaces((prev) =>
      prev.map((w) => (w.id === normalized.id ? { ...w, ...normalized } : w))
    )
    showToast(`Updated workspace "${normalized.name}"`)
  }

  const handleWorkspaceDeleted = (deletedId) => {
    setWorkspaces((prev) => prev.filter((w) => w.id !== deletedId))
    showToast('Workspace deleted')
  }

  const handleWorkspaceClick = (id) => {
    navigate(`/w/${id}/chat`)
  }

  return (
    <div className="min-h-screen w-full bg-[#F8F8F6] text-[#18181B] p-4 sm:p-8 lg:p-10 font-sans overflow-y-auto selection:bg-zinc-200 selection:text-zinc-900">
      <header className="max-w-6xl mx-auto flex items-center justify-between border-b border-[#E4E4E0] pb-6 mb-8 select-none">
        <div className="flex items-center space-x-3.5">
          <div className="w-10 h-10 rounded-xl bg-[#18181B] text-white border border-[#18181B] flex items-center justify-center shadow-xs shrink-0">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <h1 className="font-display font-bold text-xl sm:text-2xl text-[#18181B] tracking-tight">
              CollabAI Workspaces
            </h1>
            <p className="text-[#52525B] text-xs mt-0.5">
              Select a workspace or create a new team environment
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2 sm:space-x-3">
          <button
            type="button"
            onClick={openCreateModal}
            className="btn-primary flex items-center space-x-1.5 text-xs sm:text-sm cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            <span className="hidden xs:inline">New Workspace</span>
            <span className="xs:hidden">New</span>
          </button>

          <NotificationCenter onWorkspaceChange={() => refreshWorkspaces()} />

          <button
            type="button"
            onClick={async () => {
              await logout()
              navigate('/login')
            }}
            className="inline-flex items-center space-x-1 text-[#52525B] hover:text-[#DC2626] hover:bg-[#FEE2E2]/50 px-3 py-2 rounded-xl text-xs sm:text-sm font-semibold transition-colors cursor-pointer"
            title="Log Out"
          >
            <LogOut className="w-4 h-4" />
            <span className="hidden sm:inline">Log Out</span>
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="max-w-6xl mx-auto">
        {loadingList ? (
          <div className="bg-white border border-[#E4E4E0] rounded-2xl p-12 text-center text-sm text-[#52525B] shadow-xs flex flex-col items-center justify-center space-y-3">
            <div className="w-6 h-6 border-2 border-[#18181B] border-t-transparent rounded-full animate-spin" />
            <span>Loading workspaces...</span>
          </div>
        ) : workspaces.length === 0 ? (
          <div className="bg-white border border-[#E4E4E0] rounded-2xl p-8 sm:p-12 text-center max-w-xl mx-auto mt-12 flex flex-col items-center shadow-xs">
            <div className="w-12 h-12 rounded-2xl bg-[#18181B] flex items-center justify-center text-white mb-4">
              <Briefcase className="w-6 h-6" />
            </div>
            <h3 className="font-display font-bold text-lg text-[#18181B]">
              No workspaces found
            </h3>
            <p className="text-[#52525B] text-xs max-w-sm mt-1.5 mb-6 leading-relaxed">
              Create your first team workspace to start organizing documents, tracking tasks, and collaborating with context-aware AI agents.
            </p>
            <button
              type="button"
              onClick={openCreateModal}
              className="btn-primary flex items-center cursor-pointer"
            >
              <Plus className="w-4 h-4 mr-1.5" />
              <span>Create First Workspace</span>
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {workspaces.map((ws) => {
              const isOwner = ws.role === 'owner' || ws.owner_id === currentUserId
              return (
                <motion.div
                  key={ws.id}
                  whileHover={{ y: -2 }}
                  onClick={() => handleWorkspaceClick(ws.id)}
                  className="bg-white border border-[#E4E4E0] rounded-2xl p-5 sm:p-6 flex flex-col justify-between hover:border-[#18181B] hover:shadow-md cursor-pointer transition-all group duration-150 relative"
                >
                  <div>
                    {/* Top Row: Avatar Initials + Open Indicator + Three-dot Menu */}
                    <div className="flex items-center justify-between mb-3">
                      <span className="w-8 h-8 rounded-lg bg-[#18181B] text-white border border-[#18181B] flex items-center justify-center font-bold text-xs">
                        {ws.name.substring(0, 2).toUpperCase()}
                      </span>

                      <div className="flex items-center space-x-1.5">
                        <span className="text-[11px] font-mono text-[#71717A] group-hover:text-[#18181B] flex items-center space-x-0.5">
                          <span>Open</span>
                          <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                        </span>

                        <WorkspaceCardMenu
                          workspace={ws}
                          isOwner={isOwner}
                          onEdit={(target) => setEditingWorkspace(target)}
                          onDelete={(target) => setDeletingWorkspace(target)}
                        />
                      </div>
                    </div>

                    <h3 className="font-display font-bold text-base text-[#18181B] group-hover:text-[#18181B] transition-colors truncate">
                      {ws.name}
                    </h3>
                    <div className="mt-1 text-[#52525B] text-xs line-clamp-2 min-h-8 leading-relaxed">
                      {ws.description || 'No description provided.'}
                    </div>
                  </div>

                  <div className="flex items-center justify-between mt-6 pt-4 border-t border-[#E4E4E0] text-xs text-[#52525B]">
                    <div className="flex items-center space-x-1.5 bg-[#F4F4F5] px-2 py-0.5 rounded-md border border-[#E4E4E0]">
                      <Users className="w-3.5 h-3.5 text-[#52525B]" />
                      <span>
                        {ws.member_count} {ws.member_count === 1 ? 'member' : 'members'}
                      </span>
                    </div>

                    <div className="flex items-center space-x-1 text-[#18181B] text-[11px] font-medium">
                      <Clock className="w-3 h-3 text-[#52525B]" />
                      <span>{isOwner ? 'Owner' : 'Member'}</span>
                    </div>
                  </div>
                </motion.div>
              )
            })}
          </div>
        )}
      </main>

      {/* Modals */}
      <CreateWorkspaceModal
        isOpen={showCreateModal}
        onClose={closeCreateModal}
        onSubmit={handleCreate}
        creating={creating}
        submitError={submitError}
        onClearSubmitError={() => setSubmitError('')}
      />

      <EditWorkspaceModal
        isOpen={Boolean(editingWorkspace)}
        workspace={editingWorkspace}
        onClose={() => setEditingWorkspace(null)}
        onSaved={handleWorkspaceSaved}
      />

      <DeleteWorkspaceModal
        isOpen={Boolean(deletingWorkspace)}
        workspace={deletingWorkspace}
        onClose={() => setDeletingWorkspace(null)}
        onDeleted={handleWorkspaceDeleted}
      />

      {/* Toast Feedback */}
      <AnimatePresence>
        {toastMessage && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            className="fixed bottom-6 right-6 z-50 px-4 py-2.5 rounded-xl text-xs font-semibold shadow-xl border bg-[#18181B] text-white border-[#27272A]"
          >
            {toastMessage}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default Workspaces
