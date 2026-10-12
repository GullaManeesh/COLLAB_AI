import React, { useState, useRef, useEffect } from 'react'
import { MoreVertical, Pencil, Trash2 } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

const WorkspaceCardMenu = ({
  workspace,
  isOwner,
  onEdit,
  onDelete,
}) => {
  const [isOpen, setIsOpen] = useState(false)
  const menuRef = useRef(null)

  useEffect(() => {
    if (!isOpen) return

    const handlePointerDown = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setIsOpen(false)
      }
    }

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        setIsOpen(false)
      }
    }

    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)

    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen])

  const handleToggle = (e) => {
    e.stopPropagation()
    setIsOpen((prev) => !prev)
  }

  const handleEditClick = (e) => {
    e.stopPropagation()
    setIsOpen(false)
    if (isOwner) {
      onEdit?.(workspace)
    }
  }

  const handleDeleteClick = (e) => {
    e.stopPropagation()
    setIsOpen(false)
    if (isOwner) {
      onDelete?.(workspace)
    }
  }

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        onClick={handleToggle}
        aria-label={`Actions for workspace ${workspace.name}`}
        aria-expanded={isOpen}
        className={`p-1.5 rounded-lg text-[#71717A] hover:text-[#18181B] hover:bg-[#F4F4F5] transition-all cursor-pointer opacity-70 group-hover:opacity-100 ${
          isOpen ? 'bg-[#F4F4F5] opacity-100 text-[#18181B]' : ''
        }`}
      >
        <MoreVertical className="w-4 h-4" />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -4 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -4 }}
            transition={{ duration: 0.12 }}
            onClick={(e) => e.stopPropagation()}
            className="absolute right-0 top-full mt-1 w-44 rounded-xl border border-[#E4E4E0] bg-white p-1 shadow-lg z-30 select-none"
          >
            {isOwner ? (
              <>
                <button
                  type="button"
                  onClick={handleEditClick}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium text-[#18181B] hover:bg-[#F4F4F5] rounded-lg transition-colors cursor-pointer text-left"
                >
                  <Pencil className="w-3.5 h-3.5 text-[#71717A]" />
                  <span>Edit workspace</span>
                </button>
                <div className="h-px bg-[#F0F0EE] my-1" />
                <button
                  type="button"
                  onClick={handleDeleteClick}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium text-[#DC2626] hover:bg-[#FEF2F2] rounded-lg transition-colors cursor-pointer text-left"
                >
                  <Trash2 className="w-3.5 h-3.5 text-[#DC2626]" />
                  <span>Delete workspace</span>
                </button>
              </>
            ) : (
              <div className="px-3 py-2 text-[11px] text-[#71717A] leading-relaxed">
                Only the workspace owner can edit or delete this workspace.
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default WorkspaceCardMenu
