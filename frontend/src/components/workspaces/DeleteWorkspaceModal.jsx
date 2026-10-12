import React, { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Trash2, X, AlertTriangle } from 'lucide-react'
import api from '../../api/client'

const DeleteWorkspaceModal = ({
  isOpen,
  workspace,
  onClose,
  onDeleted,
}) => {
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (isOpen) {
      setError('')
    }
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && !deleting) {
        e.preventDefault()
        onClose?.()
      }
    }

    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', handleKeyDown)

    return () => {
      document.body.style.overflow = prevOverflow
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen, deleting, onClose])

  const handleDelete = async () => {
    if (deleting || !workspace?.id) return

    setDeleting(true)
    setError('')

    try {
      await api.delete(`/api/workspaces/${workspace.id}`)
      onDeleted?.(workspace.id)
      onClose?.()
    } catch (err) {
      const detail = err?.response?.data?.detail
      setError(
        typeof detail === 'string'
          ? detail
          : 'Failed to delete workspace. Please try again.'
      )
    } finally {
      setDeleting(false)
    }
  }

  return (
    <AnimatePresence>
      {isOpen && workspace && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-50 bg-[#18181B]/45 backdrop-blur-[2px] p-3 sm:p-6 overflow-y-auto flex items-center justify-center select-none"
          onClick={() => {
            if (!deleting) onClose?.()
          }}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-workspace-title"
            initial={{ opacity: 0, y: 10, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.98 }}
            transition={{ duration: 0.18 }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md my-auto rounded-2xl border border-[#FCA5A5]/60 bg-white shadow-2xl flex flex-col overflow-hidden text-left"
          >
            {/* Header */}
            <div className="flex items-start justify-between gap-4 border-b border-[#FEE2E2] px-5 py-5 sm:px-6 shrink-0 bg-[#FEF2F2]/40">
              <div className="flex items-start gap-3.5">
                <div className="w-10 h-10 rounded-xl bg-[#DC2626] text-white flex items-center justify-center shrink-0 shadow-xs">
                  <Trash2 className="w-5 h-5" />
                </div>
                <div>
                  <h2
                    id="delete-workspace-title"
                    className="font-display font-bold text-lg text-[#18181B] leading-tight tracking-tight"
                  >
                    Delete Workspace
                  </h2>
                  <p className="text-xs text-[#71717A] mt-1">
                    This action is permanent and cannot be undone.
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={onClose}
                disabled={deleting}
                aria-label="Close delete modal"
                className="rounded-lg p-1.5 text-[#71717A] hover:bg-white hover:text-[#18181B] transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Body */}
            <div className="p-5 sm:p-6 space-y-4">
              {error && (
                <div
                  role="alert"
                  className="rounded-xl border border-[#FCA5A5] bg-[#FEF2F2] p-3 text-xs text-[#991B1B]"
                >
                  {error}
                </div>
              )}

              <div className="rounded-xl border border-[#FEE2E2] bg-[#FEF2F2]/50 p-4 space-y-2">
                <div className="flex items-center gap-2 text-xs font-semibold text-[#991B1B]">
                  <AlertTriangle className="w-4 h-4 text-[#DC2626] shrink-0" />
                  <span>Warning: All associated data will be removed</span>
                </div>
                <p className="text-xs text-[#7F1D1D] leading-relaxed">
                  Are you sure you want to delete{' '}
                  <strong className="font-semibold text-[#18181B]">
                    "{workspace.name}"
                  </strong>
                  ? All channels, messages, documents, and invitations belonging to this workspace will be deleted immediately.
                </p>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-[#F0F0EE]">
                <button
                  type="button"
                  onClick={onClose}
                  disabled={deleting}
                  className="btn-secondary text-xs px-4 py-2 cursor-pointer disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleDelete}
                  disabled={deleting}
                  className="bg-[#DC2626] hover:bg-[#B91C1C] text-white text-xs font-semibold px-4 py-2 rounded-xl transition-colors cursor-pointer disabled:opacity-50 flex items-center gap-1.5 shadow-xs"
                >
                  {deleting ? (
                    <>
                      <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      <span>Deleting...</span>
                    </>
                  ) : (
                    <span>Delete Workspace</span>
                  )}
                </button>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export default DeleteWorkspaceModal
