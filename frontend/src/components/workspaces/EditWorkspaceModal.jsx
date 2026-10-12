import React, { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Pencil, X, AlertCircle } from 'lucide-react'
import api from '../../api/client'

const EditWorkspaceModal = ({
  isOpen,
  workspace,
  onClose,
  onSaved,
}) => {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [nameError, setNameError] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [saving, setSaving] = useState(false)

  const nameInputRef = useRef(null)

  useEffect(() => {
    if (isOpen && workspace) {
      setName(workspace.name || '')
      setDescription(workspace.description || '')
      setNameError('')
      setSubmitError('')
      requestAnimationFrame(() => {
        nameInputRef.current?.focus()
      })
    }
  }, [isOpen, workspace])

  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && !saving) {
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
  }, [isOpen, saving, onClose])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (saving || !workspace?.id) return

    const trimmedName = name.trim()
    const trimmedDescription = description.trim()

    if (!trimmedName) {
      setNameError('Workspace name cannot be empty.')
      nameInputRef.current?.focus()
      return
    }

    setSaving(true)
    setSubmitError('')

    try {
      const response = await api.patch(`/api/workspaces/${workspace.id}`, {
        name: trimmedName,
        description: trimmedDescription,
      })

      const updated = response?.data || {
        ...workspace,
        name: trimmedName,
        description: trimmedDescription,
      }

      onSaved?.(updated)
      onClose?.()
    } catch (err) {
      const detail = err?.response?.data?.detail
      setSubmitError(
        typeof detail === 'string'
          ? detail
          : 'Failed to update workspace. Please try again.'
      )
    } finally {
      setSaving(false)
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
            if (!saving) onClose?.()
          }}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="edit-workspace-title"
            initial={{ opacity: 0, y: 10, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.98 }}
            transition={{ duration: 0.18 }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-lg my-auto rounded-2xl border border-[#E4E4E0] bg-white shadow-2xl flex flex-col overflow-hidden text-left"
          >
            {/* Header */}
            <div className="flex items-start justify-between gap-4 border-b border-[#F0F0EE] px-5 py-5 sm:px-6 shrink-0 bg-white">
              <div className="flex items-start gap-3.5">
                <div className="w-10 h-10 rounded-xl bg-[#18181B] text-white flex items-center justify-center shrink-0 shadow-xs">
                  <Pencil className="w-5 h-5" />
                </div>
                <div>
                  <h2
                    id="edit-workspace-title"
                    className="font-display font-bold text-lg text-[#18181B] leading-tight tracking-tight"
                  >
                    Edit Workspace
                  </h2>
                  <p className="text-xs text-[#52525B] mt-1">
                    Update the workspace name and description.
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={onClose}
                disabled={saving}
                aria-label="Close edit workspace modal"
                className="rounded-lg p-1.5 text-[#71717A] hover:bg-[#F4F4F5] hover:text-[#18181B] transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Form */}
            <form onSubmit={handleSubmit} className="p-5 sm:p-6 space-y-4">
              {submitError && (
                <div
                  role="alert"
                  className="flex items-start gap-2.5 rounded-xl border border-[#FCA5A5] bg-[#FEF2F2] p-3 text-xs text-[#991B1B]"
                >
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-[#DC2626]" />
                  <span>{submitError}</span>
                </div>
              )}

              <div className="space-y-1.5">
                <label
                  htmlFor="edit-workspace-name"
                  className="block text-xs font-semibold text-[#18181B]"
                >
                  Workspace Name <span className="text-[#DC2626]">*</span>
                </label>
                <input
                  id="edit-workspace-name"
                  ref={nameInputRef}
                  type="text"
                  required
                  maxLength={100}
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value)
                    if (nameError) setNameError('')
                    if (submitError) setSubmitError('')
                  }}
                  className={`w-full rounded-xl border bg-[#F8F8F6] px-3.5 py-2.5 text-sm text-[#18181B] placeholder:text-[#A1A1AA] transition-all focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#18181B]/10 ${
                    nameError
                      ? 'border-[#DC2626] focus:border-[#DC2626]'
                      : 'border-[#E4E4E0] focus:border-[#18181B]'
                  }`}
                />
                {nameError && (
                  <p className="text-xs text-[#DC2626] mt-1">{nameError}</p>
                )}
              </div>

              <div className="space-y-1.5">
                <label
                  htmlFor="edit-workspace-desc"
                  className="block text-xs font-semibold text-[#18181B]"
                >
                  Description
                </label>
                <textarea
                  id="edit-workspace-desc"
                  rows={3}
                  maxLength={1000}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="What is this workspace focused on?"
                  className="w-full rounded-xl border border-[#E4E4E0] bg-[#F8F8F6] px-3.5 py-2.5 text-sm text-[#18181B] placeholder:text-[#A1A1AA] transition-all focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#18181B]/10 focus:border-[#18181B] resize-none"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-[#F0F0EE]">
                <button
                  type="button"
                  onClick={onClose}
                  disabled={saving}
                  className="btn-secondary text-xs px-4 py-2 cursor-pointer disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving || !name.trim()}
                  className="btn-primary text-xs px-5 py-2 cursor-pointer disabled:opacity-50 flex items-center gap-1.5"
                >
                  {saving ? (
                    <>
                      <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      <span>Saving...</span>
                    </>
                  ) : (
                    <span>Save Changes</span>
                  )}
                </button>
              </div>
            </form>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export default EditWorkspaceModal
