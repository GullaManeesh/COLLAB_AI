import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { AlertCircle, AlertTriangle, LoaderCircle, Trash2, X } from 'lucide-react'
import api from '../../api/client'

export default function DeleteDocumentModal({
  isOpen,
  document,
  workspaceId,
  onClose,
  onDeleted,
}) {
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (isOpen) setError('')
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return undefined

    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && !deleting) {
        event.preventDefault()
        onClose?.()
      }
    }

    const previousOverflow = window.document.body.style.overflow
    window.document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', handleKeyDown)

    return () => {
      window.document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen, deleting, onClose])

  const handleDelete = async () => {
    if (deleting || !document?.id || !workspaceId) return

    setDeleting(true)
    setError('')

    try {
      await api.delete(`/api/workspaces/${workspaceId}/documents/${document.id}`)
      onDeleted?.(document)
    } catch (err) {
      const detail = err?.response?.data?.detail
      setError(
        typeof detail === 'string'
          ? detail
          : 'Failed to delete the document. Please try again.',
      )
    } finally {
      setDeleting(false)
    }
  }

  return (
    <AnimatePresence>
      {isOpen && document && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-[#18181B]/45 p-3 backdrop-blur-[2px] sm:p-6"
          onClick={() => {
            if (!deleting) onClose?.()
          }}
        >
          <motion.div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-document-title"
            aria-describedby="delete-document-description"
            initial={{ opacity: 0, y: 10, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.98 }}
            transition={{ duration: 0.18 }}
            onClick={(event) => event.stopPropagation()}
            className="my-auto flex w-full max-w-md flex-col overflow-hidden rounded-2xl border border-[#FCA5A5]/60 bg-white text-left shadow-2xl"
          >
            <div className="flex shrink-0 items-start justify-between gap-4 border-b border-[#FEE2E2] bg-[#FEF2F2]/40 px-5 py-5 sm:px-6">
              <div className="flex items-start gap-3.5">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#DC2626] text-white shadow-xs">
                  <Trash2 className="h-5 w-5" />
                </div>
                <div>
                  <h2
                    id="delete-document-title"
                    className="font-display text-lg font-bold leading-tight tracking-tight text-[#18181B]"
                  >
                    Delete Document
                  </h2>
                  <p className="mt-1 text-xs text-[#71717A]">
                    This action is permanent and cannot be undone.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={onClose}
                disabled={deleting}
                aria-label="Close delete document dialog"
                className="cursor-pointer rounded-lg p-1.5 text-[#71717A] transition-colors hover:bg-white hover:text-[#18181B] disabled:cursor-not-allowed disabled:opacity-40"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-4 p-5 sm:p-6">
              {error && (
                <div
                  role="alert"
                  className="flex items-start gap-2.5 rounded-xl border border-[#FCA5A5] bg-[#FEF2F2] p-3 text-xs text-[#991B1B]"
                >
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-[#DC2626]" />
                  <span>{error}</span>
                </div>
              )}

              <div className="space-y-2 rounded-xl border border-[#FEE2E2] bg-[#FEF2F2]/50 p-4">
                <div className="flex items-center gap-2 text-xs font-semibold text-[#991B1B]">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-[#DC2626]" />
                  <span>The document and its stored chunks will be removed</span>
                </div>
                <p id="delete-document-description" className="break-words text-xs leading-relaxed text-[#7F1D1D]">
                  Are you sure you want to delete{' '}
                  <strong className="font-semibold text-[#18181B]">“{document.filename}”</strong>?
                  This also removes its extracted text and embedding vectors from this workspace.
                </p>
              </div>

              <div className="flex items-center justify-end gap-3 border-t border-[#F0F0EE] pt-3">
                <button
                  type="button"
                  onClick={onClose}
                  disabled={deleting}
                  className="btn-secondary cursor-pointer px-4 py-2 text-xs disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleDelete}
                  disabled={deleting}
                  className="flex cursor-pointer items-center gap-1.5 rounded-xl bg-[#DC2626] px-4 py-2 text-xs font-semibold text-white shadow-xs transition-colors hover:bg-[#B91C1C] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {deleting ? (
                    <>
                      <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                      <span>Deleting...</span>
                    </>
                  ) : (
                    <span>Delete Document</span>
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
