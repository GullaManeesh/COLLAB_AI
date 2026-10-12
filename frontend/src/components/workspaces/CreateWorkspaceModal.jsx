import React, { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Plus, X, UserPlus, Mail, AlertCircle } from 'lucide-react'
import api from '../../api/client'

// Robust email validation regex
const EMAIL_REGEX = /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$/

const CreateWorkspaceModal = ({
  isOpen,
  onClose,
  onSubmit,
  creating = false,
  submitError = '',
  onClearSubmitError,
}) => {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [emailInput, setEmailInput] = useState('')
  const [invitees, setInvitees] = useState([])
  const [nameError, setNameError] = useState('')
  const [emailError, setEmailError] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [searchingTeammates, setSearchingTeammates] = useState(false) 

  const nameInputRef = useRef(null)
  const emailInputRef = useRef(null)
  const dialogRef = useRef(null)

  // Reset form when opening modal
  useEffect(() => {
    if (isOpen) {
      setName('')
      setDescription('')
      setEmailInput('')
      setInvitees([])
      setNameError('')
      setEmailError('')
      onClearSubmitError?.()

      // Focus first input
      requestAnimationFrame(() => {
        nameInputRef.current?.focus()
      })
    }
  }, [isOpen])

  
useEffect(() => {
  const query = emailInput.trim()

  if (!isOpen || query.length < 2) {
    setSuggestions([])
    return
  }

  let cancelled = false

  const timer = setTimeout(async () => {
    setSearchingTeammates(true)

    try {
      const response = await api.get('/api/workspaces/teammates/search', {
        params: { q: query },
      })

      if (!cancelled) {
        setSuggestions(response.data?.suggestions || [])
      }
    } catch {
      if (!cancelled) {
        setSuggestions([])
      }
    } finally {
      if (!cancelled) {
        setSearchingTeammates(false)
      }
    }
  }, 250)

  return () => {
    cancelled = true
    clearTimeout(timer)
  }
}, [emailInput, isOpen])


  // Keyboard navigation & body scroll lock
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && !creating) {
        e.preventDefault()
        onClose?.()
      }
    }

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', handleKeyDown)

    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen, creating, onClose])

  const handleAddInvitee = () => {
    const trimmed = emailInput.trim()

    if (!trimmed) {
      setEmailError('Please enter an email address.')
      emailInputRef.current?.focus()
      return
    }

    if (!EMAIL_REGEX.test(trimmed)) {
      setEmailError('Please enter a valid email address (e.g. alex@company.com).')
      emailInputRef.current?.focus()
      return
    }

    const isDuplicate = invitees.some(
      (item) => item.toLowerCase() === trimmed.toLowerCase()
    )

    if (isDuplicate) {
      setEmailError('This email address has already been added.')
      emailInputRef.current?.focus()
      return
    }

    setInvitees((prev) => [...prev, trimmed])
    setEmailInput('')
    setEmailError('')
    emailInputRef.current?.focus()
  }

  const handleSelectSuggestion = (person) => {
    const emailToAdd = person.email.trim().toLowerCase()
    const isDuplicate = invitees.some((item) => item.toLowerCase() === emailToAdd)
    if (isDuplicate) {
      setEmailError('This teammate is already in the invitation list.')
      setSuggestions([])
      return
    }
    setInvitees((prev) => [...prev, emailToAdd])
    setEmailInput('')
    setSuggestions([])
    setEmailError('')
    emailInputRef.current?.focus()
  }

  const handleRemoveInvitee = (emailToRemove) => {
    setInvitees((prev) => prev.filter((item) => item.toLowerCase() !== emailToRemove.toLowerCase()))
    if (emailError) {
      setEmailError('')
    }
  }

  const handleEmailKeyDown = (e) => {
    if (e.key === 'Enter') {
      // Prevent form submission on Enter in email field
      e.preventDefault()
      e.stopPropagation()
      handleAddInvitee()
    }
  }

  const handleFormSubmit = async (e) => {
    e.preventDefault()
    if (creating) return

    const trimmedName = name.trim()
    const trimmedDescription = description.trim()

    if (!trimmedName) {
      setNameError('Workspace name is required.')
      nameInputRef.current?.focus()
      return
    }

    // If user has typed something in email input but forgot to click Add
    const leftoverEmail = emailInput.trim()
    let currentInvitees = [...invitees]

    if (leftoverEmail) {
      if (EMAIL_REGEX.test(leftoverEmail)) {
        const isDuplicate = invitees.some(
          (item) => item.toLowerCase() === leftoverEmail.toLowerCase()
        )
        if (!isDuplicate) {
          currentInvitees.push(leftoverEmail)
          setInvitees(currentInvitees)
          setEmailInput('')
          setEmailError('')
        }
      } else {
        setEmailError('Please complete or clear this email address before submitting.')
        emailInputRef.current?.focus()
        return
      }
    }

    onSubmit?.({
      name: trimmedName,
      description: trimmedDescription,
      invitees: currentInvitees,
    })
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-50 bg-[#18181B]/45 backdrop-blur-[2px] p-3 sm:p-6 overflow-y-auto flex items-center justify-center select-none"
          onClick={() => {
            if (!creating) onClose?.()
          }}
        >
          <motion.div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-workspace-title"
            aria-describedby="create-workspace-subtitle"
            initial={{ opacity: 0, y: 10, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.98 }}
            transition={{ duration: 0.18 }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-xl my-auto rounded-2xl border border-[#E4E4E0] bg-white shadow-2xl flex max-h-[calc(100dvh-2rem)] sm:max-h-[calc(100dvh-3rem)] flex-col overflow-hidden text-left"
          >
            {/* Header */}
            <div className="flex items-start justify-between gap-4 border-b border-[#F0F0EE] px-5 py-5 sm:px-6 shrink-0 bg-white">
              <div className="flex items-start gap-3.5">
                <div className="w-10 h-10 rounded-xl bg-[#18181B] text-white flex items-center justify-center shrink-0 shadow-xs">
                  <Plus className="w-5 h-5" />
                </div>
                <div>
                  <h2
                    id="create-workspace-title"
                    className="font-display font-bold text-lg text-[#18181B] leading-tight tracking-tight"
                  >
                    Create Workspace
                  </h2>
                  <p
                    id="create-workspace-subtitle"
                    className="text-xs text-[#52525B] mt-1"
                  >
                    Set up a team room for documents, chat, and AI copilot.
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={onClose}
                disabled={creating}
                className="rounded-lg p-1.5 text-[#71717A] hover:bg-[#F4F4F5] hover:text-[#18181B] transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                aria-label="Close create workspace modal"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Scrollable Form Body */}
            <form onSubmit={handleFormSubmit} className="flex flex-1 min-h-0 flex-col">
              <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4 sm:space-y-5">
                {/* Workspace Name Field */}
                <div className="space-y-1.5">
                  <label
                    htmlFor="workspace-name-input"
                    className="block text-xs font-semibold text-[#18181B]"
                  >
                    Workspace Name <span className="text-[#DC2626]">*</span>
                  </label>
                  <input
                    id="workspace-name-input"
                    ref={nameInputRef}
                    type="text"
                    required
                    maxLength={120}
                    value={name}
                    onChange={(e) => {
                      setName(e.target.value)
                      if (nameError) setNameError('')
                      onClearSubmitError?.()
                    }}
                    placeholder="e.g. Mobile App Revamp"
                    aria-invalid={Boolean(nameError)}
                    aria-describedby={nameError ? 'workspace-name-error' : undefined}
                    className={`w-full rounded-xl border bg-[#F8F8F6] px-3.5 py-2.5 text-sm text-[#18181B] placeholder:text-[#A1A1AA] transition-all focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#18181B]/10 ${
                      nameError
                        ? 'border-[#DC2626] focus:border-[#DC2626]'
                        : 'border-[#E4E4E0] focus:border-[#18181B]'
                    }`}
                  />
                  {nameError && (
                    <p id="workspace-name-error" className="text-xs text-[#DC2626] mt-1">
                      {nameError}
                    </p>
                  )}
                </div>

                {/* Description Field */}
                <div className="space-y-1.5">
                  <label
                    htmlFor="workspace-description-input"
                    className="block text-xs font-semibold text-[#18181B]"
                  >
                    Description
                  </label>
                  <textarea
                    id="workspace-description-input"
                    rows={3}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="What is this workspace focused on?"
                    className="w-full rounded-xl border border-[#E4E4E0] bg-[#F8F8F6] px-3.5 py-2.5 text-sm text-[#18181B] placeholder:text-[#A1A1AA] transition-all focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#18181B]/10 focus:border-[#18181B] resize-none"
                  />
                </div>

                {/* Invite Team Members Section */}
                <div className="pt-2 border-t border-[#F0F0EE] space-y-2.5">
                  <div>
                    <h3 className="text-xs font-semibold text-[#18181B]">
                      Invite Team Members
                    </h3>
                    <p className="text-[11px] sm:text-xs text-[#71717A] mt-0.5 leading-relaxed">
                      Bring your team into this workspace. You can also invite members later from workspace settings.
                    </p>
                  </div>

                  {/* Email Input + Add Button */}
                  <div className="space-y-1.5">
                    <div className="flex items-center gap-2">
                      <div className="relative flex-1">
                        <input
                          id="invitee-email-input"
                          ref={emailInputRef}
                          type="email"
                          value={emailInput}
                          onChange={(e) => {
                            setEmailInput(e.target.value)
                            if (emailError) setEmailError('')
                          }}
                          onKeyDown={handleEmailKeyDown}
                          placeholder="Enter email address"
                          aria-invalid={Boolean(emailError)}
                          aria-describedby={emailError ? 'invitee-email-error' : undefined}
                          className={`w-full rounded-xl border bg-[#F8F8F6] px-3.5 py-2 text-sm text-[#18181B] placeholder:text-[#A1A1AA] transition-all focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#18181B]/10 ${
                            emailError
                              ? 'border-[#DC2626] focus:border-[#DC2626]'
                              : 'border-[#E4E4E0] focus:border-[#18181B]'
                          }`}
                        />
                        
                        {(searchingTeammates || suggestions.length > 0 || (emailInput.trim().length >= 2 && !searchingTeammates && suggestions.length === 0)) && (
                          <div className="absolute left-0 right-0 top-full mt-1.5 z-30 overflow-hidden rounded-xl border border-[#E4E4E0] bg-white shadow-xl max-h-48 overflow-y-auto">
                            {searchingTeammates && (
                              <p className="px-3 py-2 text-xs text-[#71717A]">
                                Searching registered teammates...
                              </p>
                            )}

                            {!searchingTeammates && suggestions.length === 0 && emailInput.trim().length >= 2 && (
                              <p className="px-3 py-2 text-xs text-[#71717A]">
                                No registered users found matching "{emailInput.trim()}".
                              </p>
                            )}

                            {suggestions.map((person) => (
                              <button
                                key={person.user_id}
                                type="button"
                                onClick={() => handleSelectSuggestion(person)}
                                className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-[#F4F4F5] transition-colors cursor-pointer border-b border-[#F4F4F2] last:border-0"
                              >
                                <div className="flex items-center space-x-2.5 min-w-0 pr-2">
                                  <div className="w-7 h-7 rounded-full bg-[#18181B] text-white flex items-center justify-center font-bold text-xs shrink-0">
                                    {(person.name || person.email).charAt(0).toUpperCase()}
                                  </div>
                                  <div className="flex flex-col min-w-0">
                                    <span className="text-xs font-semibold text-[#18181B] truncate">
                                      {person.name || person.username || person.email}
                                    </span>
                                    <span className="text-[11px] text-[#71717A] truncate">
                                      {person.email}
                                    </span>
                                  </div>
                                </div>
                                <span className="text-[10px] font-semibold text-[#18181B] bg-[#F4F4F5] px-2 py-0.5 rounded-md shrink-0">
                                  + Add
                                </span>
                              </button>
                            ))}
                          </div>
                        )}

                      </div>

                      <button
                        type="button"
                        onClick={handleAddInvitee}
                        className="btn-secondary text-xs px-3.5 py-2 flex items-center space-x-1.5 shrink-0 cursor-pointer hover:bg-[#F4F4F5] active:scale-97 transition-all font-semibold"
                      >
                        <Plus className="w-3.5 h-3.5 text-[#18181B]" />
                        <span>Add</span>
                      </button>
                    </div>

                    {emailError && (
                      <p id="invitee-email-error" className="text-xs text-[#DC2626]">
                        {emailError}
                      </p>
                    )}
                  </div>

                  {/* Invitee List / Empty State */}
                  <div className="mt-2">
                    {invitees.length === 0 ? (
                      <div className="flex items-center space-x-2.5 px-3 py-2.5 rounded-xl border border-dashed border-[#E4E4E0] bg-[#FAFAF9] text-[#71717A] text-xs">
                        <UserPlus className="w-4 h-4 text-[#A1A1AA] shrink-0" />
                        <span>No members added yet. Enter email addresses above to add them to this workspace.</span>
                      </div>
                    ) : (
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between text-[11px] text-[#71717A] px-0.5">
                          <span>Pending Invitees ({invitees.length})</span>
                          <span className="text-[10px] text-[#A1A1AA]">
                            Press Add or Enter to queue
                          </span>
                        </div>
                        <div className="max-h-36 overflow-y-auto space-y-1.5 pr-0.5">
                          {invitees.map((email) => (
                            <div
                              key={email}
                              className="flex items-center justify-between px-3 py-1.5 rounded-xl border border-[#E4E4E0] bg-[#FAFAF9] hover:bg-white hover:border-[#D4D4D0] transition-colors text-xs"
                            >
                              <div className="flex items-center space-x-2.5 min-w-0 pr-2">
                                <div className="w-6 h-6 rounded-full bg-[#18181B] text-white flex items-center justify-center font-bold text-[10px] shrink-0">
                                  {email.charAt(0).toUpperCase()}
                                </div>
                                <span className="font-medium text-[#18181B] truncate">
                                  {email}
                                </span>
                              </div>

                              <button
                                type="button"
                                onClick={() => handleRemoveInvitee(email)}
                                aria-label={`Remove ${email}`}
                                className="p-1 rounded-lg text-[#71717A] hover:text-[#DC2626] hover:bg-[#FEE2E2] transition-colors cursor-pointer shrink-0"
                              >
                                <X className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Submit Error Box */}
                {submitError && (
                  <div
                    className="rounded-xl border border-[#FECACA] bg-[#FEF2F2] p-3 text-xs text-[#B91C1C] flex items-start space-x-2"
                    role="alert"
                  >
                    <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                    <span className="leading-relaxed">{submitError}</span>
                  </div>
                )}
              </div>

              {/* Modal Footer */}
              <div className="border-t border-[#F0F0EE] px-4 py-3.5 sm:px-6 sm:py-4 bg-white shrink-0 rounded-b-2xl">
                <div className="flex flex-col-reverse sm:flex-row items-stretch sm:items-center justify-end gap-2.5 sm:gap-3 w-full">
                  <button
                    type="button"
                    onClick={onClose}
                    disabled={creating}
                    className="w-full sm:w-auto btn-secondary text-xs sm:text-sm px-4 py-2.5 sm:py-2 justify-center font-semibold disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={creating}
                    className="w-full sm:w-auto btn-primary text-xs sm:text-sm px-5 py-2.5 sm:py-2 justify-center font-semibold cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 shadow-xs hover:shadow-sm"
                  >
                    {creating ? 'Creating...' : 'Create Workspace'}
                  </button>
                </div>
              </div>
            </form>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export default CreateWorkspaceModal
