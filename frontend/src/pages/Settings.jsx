import React, { useEffect, useState } from 'react'
import { useParams, useOutletContext } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import api from '../api/client'
import usePolling from '../hooks/usePolling'
import { Users, UserPlus, UserMinus, Shield, Mail, Calendar, Settings as SettingsIcon, CheckCircle2, AlertCircle } from 'lucide-react'

const Settings = () => {
  const { id } = useParams()
  const { workspace } = useOutletContext() || {}
  const { user } = useAuth()
  const [members, setMembers] = useState(workspace?.members || [])
  const [invitations, setInvitations] = useState([])
  const [loadingInvitations, setLoadingInvitations] = useState(true)
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const isOwner = String(workspace?.owner_id || '') === String(user?.id || user?._id || '')

  useEffect(() => setMembers(workspace?.members || []), [workspace?.members])

  const refreshInvitations = async () => {
    try {
      const response = await api.get(`/api/workspaces/${id}/invitations`)
      setInvitations(response.data || [])
      setError(null)
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not load pending invitations.')
    } finally {
      setLoadingInvitations(false)
    }
  }

  useEffect(() => {
    if (!isOwner) {
      setLoadingInvitations(false)
      return undefined
    }
    let active = true
    api.get(`/api/workspaces/${id}/invitations`)
      .then(({ data }) => { if (active) setInvitations(data || []) })
      .catch((err) => { if (active) setError(err?.response?.data?.detail || 'Could not load pending invitations.') })
      .finally(() => { if (active) setLoadingInvitations(false) })
    return () => { active = false }
  }, [id, isOwner])

  // Keep the pending list current when an invite is accepted in another
  // browser/device, without requiring the workspace owner to reload Settings.
  usePolling(() => {
    if (isOwner) refreshInvitations()
  }, isOwner ? 3000 : null)

  const submitInvitation = async (targetEmail) => {
    if (!targetEmail.trim()) return

    setSubmitting(true)
    setError(null)
    setSuccess(null)
    
    try {
      const response = await api.post(`/api/workspaces/${id}/invitations`, { email: targetEmail.trim() })
      setEmail((current) => current.trim().toLowerCase() === targetEmail.trim().toLowerCase() ? '' : current)
      const emailStatus = response.data?.email_status
      setSuccess(emailStatus === 'accepted_by_smtp'
        ? 'Invitation created and accepted by the SMTP server.'
        : emailStatus === 'accepted_by_provider'
          ? 'Invitation created and accepted by the email provider.'
          : emailStatus === 'sending'
            ? 'Invitation created; email delivery is in progress.'
            : 'Invitation created, but email delivery failed. Check the email provider configuration and outbox.')
      await refreshInvitations()
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not create the invitation.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleAddMember = (e) => {
    e.preventDefault()
    return submitInvitation(email)
  }

  const handleRevokeInvitation = async (invitationId) => {
    setError(null)
    try {
      await api.delete(`/api/workspaces/${id}/invitations/${invitationId}`)
      setInvitations((current) => current.filter((item) => item.invitation_id !== invitationId))
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not revoke this invitation.')
    }
  }

  const handleRemoveMember = async (targetUserId) => {
    setError(null)
    setSuccess(null)
    try {
      await api.delete(`/api/workspaces/${id}/members/${targetUserId}`)
      setMembers((prev) => prev.filter((member) => String(member.user_id) !== String(targetUserId)))
      setSuccess('Member removed. Their access will be revoked on their next workspace sync.')
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not remove the workspace member.')
    }
  }

  return (
    <div className="absolute inset-0 flex flex-col bg-[#F8F8F6] text-[#18181B] h-full p-4 sm:p-6 lg:p-8 overflow-y-auto select-none">
      <div className="max-w-3xl space-y-8">
        <div>
          <h2 className="font-display font-bold text-lg sm:text-xl text-[#18181B] tracking-tight">Workspace Settings</h2>
          <p className="text-[#71717A] text-xs mt-0.5">Manage team access permissions and workspace metadata.</p>
        </div>

        {/* Workspace Info */}
        <section className="bg-white border border-[#E4E4E0] rounded-2xl p-5 sm:p-6 shadow-xs space-y-5">
          <div className="flex items-center space-x-2 border-b border-[#F4F4F2] pb-3">
            <div className="w-7 h-7 rounded-lg bg-[#F4F4F2] text-[#18181B] flex items-center justify-center shrink-0">
              <SettingsIcon className="w-4 h-4" />
            </div>
            <h3 className="font-display font-bold text-sm text-[#18181B]">General Information</h3>
          </div>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <div>
              <div className="text-[11px] font-semibold text-[#71717A] uppercase tracking-wider">Workspace Name</div>
              <div className="text-sm font-bold text-[#18181B] mt-1">{workspace?.name || 'Workspace'}</div>
            </div>

            <div>
              <div className="text-[11px] font-semibold text-[#71717A] uppercase tracking-wider">Created Date</div>
              <div className="text-xs text-[#52525B] mt-1 flex items-center space-x-1.5 font-sans">
                <Calendar className="w-3.5 h-3.5 text-[#71717A]" />
                <span>{workspace?.created_at ? new Date(workspace.created_at).toLocaleDateString() : '-'}</span>
              </div>
            </div>
            
            <div className="sm:col-span-2">
              <div className="text-[11px] font-semibold text-[#71717A] uppercase tracking-wider">Description</div>
              <div className="text-xs text-[#52525B] mt-1 select-text leading-relaxed">{workspace?.description || 'No description provided.'}</div>
            </div>
          </div>
        </section>

        {/* Member Management */}
        <section className="bg-white border border-[#E4E4E0] rounded-2xl p-5 sm:p-6 shadow-xs space-y-5">
          <div className="flex items-center space-x-2 border-b border-[#F4F4F2] pb-3">
            <div className="w-7 h-7 rounded-lg bg-[#F4F4F2] text-[#18181B] flex items-center justify-center shrink-0">
              <Users className="w-4 h-4" />
            </div>
            <h3 className="font-display font-bold text-sm text-[#18181B]">Team Members ({members.length})</h3>
          </div>

          {/* Add member by email */}
          <div className="bg-[#F8F8F6] border border-[#E4E4E0] rounded-xl p-4 space-y-3">
            <h4 className="text-xs font-semibold text-[#18181B]">Invite a Teammate</h4>
            
            {error && (
              <div className="p-2.5 bg-[#FEF2F2] border border-[#FEE2E2] text-[#991B1B] text-xs rounded-lg flex items-center space-x-1.5">
                <AlertCircle className="w-4 h-4 shrink-0 text-[#DC2626]" />
                <span>{error}</span>
              </div>
            )}
            {success && (
              <div className="p-2.5 bg-[#F0FDF4] border border-[#DCFCE7] text-[#15803D] text-xs rounded-lg flex items-center space-x-1.5">
                <CheckCircle2 className="w-4 h-4 shrink-0 text-[#15803D]" />
                <span>{success}</span>
              </div>
            )}

            <form onSubmit={handleAddMember} className="flex flex-col sm:flex-row items-stretch sm:items-center space-y-2 sm:space-y-0 sm:space-x-2.5">
              <div className="relative flex-grow">
                <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#71717A]" />
                <input 
                  type="email" 
                  required
                  disabled={!isOwner || submitting}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="teammate@company.com"
                  className="w-full bg-white border border-[#E4E4E0] text-[#18181B] text-xs sm:text-sm pl-9 pr-3 py-2 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#18181B]/10 focus:border-[#18181B] transition-all placeholder:text-[#A1A1AA]"
                />
              </div>
              <button 
                type="submit"
                disabled={!isOwner || submitting}
                className="btn-primary cursor-pointer shrink-0"
              >
                <UserPlus className="w-3.5 h-3.5 mr-1.5" />
                <span>{submitting ? 'Adding...' : 'Add Member'}</span>
              </button>
            </form>
            <div className="text-[11px] text-[#71717A]">
              Invite any email address. The recipient must sign in with that verified address and explicitly accept before getting access. Invitations expire after seven days.
            </div>
          </div>

          <div className="rounded-xl border border-[#E4E4E0] overflow-hidden">
            <div className="border-b border-[#E4E4E0] bg-[#F8F8F6] px-4 py-3 text-xs font-semibold text-[#18181B]">Pending Invitations</div>
            {loadingInvitations ? (
              <p className="p-4 text-xs text-[#71717A]">Loading invitations…</p>
            ) : invitations.length === 0 ? (
              <p className="p-4 text-xs text-[#71717A]">No pending invitations.</p>
            ) : invitations.map((invitation) => (
              <div key={invitation.invitation_id} className="flex flex-wrap items-center justify-between gap-3 border-b last:border-b-0 border-[#F4F4F2] p-3.5">
                <div className="min-w-0">
                  <div className="truncate text-xs font-semibold text-[#18181B]">{invitation.email}</div>
                  <div className="mt-1 text-[11px] text-[#71717A]">
                    Email: {{ accepted_by_provider: 'accepted by provider', accepted_by_smtp: 'accepted by SMTP server', failed: 'failed', sending: 'sending', pending: 'queued' }[invitation.email_status] || 'queued'} · Expires {invitation.expires_at ? new Date(invitation.expires_at).toLocaleDateString() : 'soon'}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {invitation.email_status === 'failed' && (
                    <button type="button" disabled={submitting} onClick={() => submitInvitation(invitation.email)} className="rounded-lg border border-[#D4D4D0] px-2.5 py-1.5 text-[11px] font-semibold disabled:opacity-50">{submitting ? 'Retrying…' : 'Retry email'}</button>
                  )}
                  {isOwner && <button type="button" onClick={() => handleRevokeInvitation(invitation.invitation_id)} className="rounded-lg px-2.5 py-1.5 text-[11px] font-semibold text-red-700 hover:bg-red-50">Revoke</button>}
                </div>
              </div>
            ))}
          </div>

          {/* Members list */}
          <div className="border border-[#E4E4E0] rounded-xl overflow-hidden divide-y divide-[#F4F4F2]">
            {members.map((m) => {
              const memberIsOwner = m.role === 'owner'
              
              return (
                <div key={m.user_id} className="p-3.5 sm:p-4 flex items-center justify-between hover:bg-[#F8F8F6] transition-colors">
                  <div className="flex items-center space-x-3 min-w-0">
                    <div 
                      className="w-8 h-8 rounded-lg flex items-center justify-center font-display font-bold text-white text-xs shrink-0 shadow-xs bg-[#18181B]"
                    >
                      {String(m.name || m.email || 'TM').substring(0, 2).toUpperCase()}
                    </div>
                    
                    <div className="truncate">
                      <div className="text-xs sm:text-sm font-bold text-[#18181B] leading-tight flex items-center space-x-1.5">
                        <span className="truncate">{m.name || m.email || 'Workspace member'}</span>
                      </div>
                      <span className="text-[11px] text-[#71717A] font-sans mt-0.5 block">
                        {m.joined_at ? `Joined ${new Date(m.joined_at).toLocaleDateString()}` : 'Member'}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center space-x-2.5 shrink-0">
                    {/* Role Badge */}
                    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded flex items-center space-x-1 uppercase tracking-wider ${
                      memberIsOwner 
                        ? 'bg-[#18181B] text-white' 
                        : 'bg-[#F4F4F2] text-[#52525B] border border-[#E4E4E0]'
                    }`}>
                      {memberIsOwner && <Shield className="w-3 h-3 text-white mr-0.5" />}
                      <span>{m.role}</span>
                    </span>

                    {/* Remove Button */}
                    {isOwner && !memberIsOwner && (
                      <button 
                        onClick={() => handleRemoveMember(m.user_id)}
                        className="text-[#71717A] hover:text-[#DC2626] p-1.5 rounded-lg hover:bg-[#FEF2F2] transition-colors cursor-pointer"
                        title="Remove member"
                      >
                        <UserMinus className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      </div>
    </div>
  )
}

export default Settings
