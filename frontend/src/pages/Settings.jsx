import React, { useEffect, useState } from 'react'
import { useParams, useOutletContext } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import api from '../api/client'
import { Users, UserPlus, UserMinus, Shield, Mail, Calendar, Settings as SettingsIcon, CheckCircle2, AlertCircle } from 'lucide-react'

const Settings = () => {
  const { id } = useParams()
  const { workspace } = useOutletContext() || {}
  const { user } = useAuth()
  const [members, setMembers] = useState(workspace?.members || [])
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const isOwner = String(workspace?.owner_id || '') === String(user?.id || user?._id || '')

  useEffect(() => setMembers(workspace?.members || []), [workspace?.members])

  const handleAddMember = async (e) => {
    e.preventDefault()
    if (!email.trim()) return

    setSubmitting(true)
    setError(null)
    setSuccess(null)
    
    try {
      const response = await api.post(`/api/workspaces/${id}/invitations`, { email: email.trim() })
      setEmail('')
      setSuccess(response.data?.email_status === 'accepted_by_smtp'
        ? 'Invitation created and accepted by the SMTP server.'
        : 'Invitation created, but email delivery failed. Check SMTP configuration and the email outbox.')
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not create the invitation.')
    } finally {
      setSubmitting(false)
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
              Invitations are limited to registered CollabAI users. Access starts after acceptance.
            </div>
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
