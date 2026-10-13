import React, { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertCircle, CheckCircle2, Layers, Mail } from 'lucide-react'
import api from '../api/client'
import { useAuth } from '../context/AuthContext'

const InvitationLanding = () => {
  const navigate = useNavigate()
  const { user, loading: authLoading, needsUsername, logout } = useAuth()
  const token = useMemo(() => window.location.hash.slice(1), [])
  const [invitation, setInvitation] = useState(null)
  const [loading, setLoading] = useState(true)
  const [accepting, setAccepting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    if (!token) {
      setError('This invitation link is missing its secure token.')
      setLoading(false)
      return () => { active = false }
    }
    window.sessionStorage.setItem('pendingInvitationToken', token)
    api.post('/api/workspaces/invitations/resolve', { token })
      .then(({ data }) => { if (active) setInvitation(data) })
      .catch((err) => {
        if (active) setError(err.response?.data?.detail || 'This invitation is invalid or expired.')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [token])

  const loginPath = '/login?next=invitation'
  const emailMatches = user?.email?.trim().toLowerCase() === invitation?.recipient_email?.trim().toLowerCase()

  const accept = async () => {
    setAccepting(true)
    setError('')
    try {
      const { data } = await api.post('/api/workspaces/invitations/accept-token', { token })
      window.sessionStorage.removeItem('pendingInvitationToken')
      navigate(`/w/${data.workspace_id}`, { replace: true })
    } catch (err) {
      setError(err.response?.data?.detail || 'The invitation could not be accepted.')
    } finally {
      setAccepting(false)
    }
  }

  const switchAccount = async () => {
    try {
      await logout()
    } catch {
      // An expired session can make server logout fail; the Google login still lets the user switch accounts.
    }
    navigate(loginPath, { replace: true })
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-[#F8F8F6] px-4 py-8 text-[#18181B]">
      <section className="w-full max-w-lg rounded-2xl border border-[#E4E4E0] bg-white p-6 shadow-xl sm:p-8">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-[#18181B] text-white"><Layers className="h-6 w-6" /></div>
          <h1 className="font-display text-2xl font-bold tracking-tight">Workspace invitation</h1>
          <p className="mt-1 text-sm text-[#71717A]">Review the invitation and accept it when you are ready.</p>
        </div>

        {loading || authLoading ? (
          <div className="py-8 text-center text-sm text-[#71717A]" role="status">Loading invitation...</div>
        ) : invitation ? (
          <div className="space-y-4">
            <div className="rounded-xl border border-[#E4E4E0] bg-[#F8F8F6] p-4">
              <p className="text-sm"><strong>{invitation.inviter_name}</strong> invited you to join</p>
              <h2 className="mt-1 text-xl font-bold">{invitation.workspace_name}</h2>
              <p className="mt-3 flex items-center gap-2 text-sm text-[#52525B]"><Mail className="h-4 w-4" />{invitation.recipient_email}</p>
              <p className="mt-3 text-xs text-[#71717A]">Expires {new Date(invitation.expires_at).toLocaleString()}</p>
            </div>

            {error && <div role="alert" className="flex gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"><AlertCircle className="h-4 w-4 shrink-0" />{error}</div>}

            {!user ? (
              <Link to={loginPath} className="btn-primary flex w-full items-center justify-center">Sign in with Google to continue</Link>
            ) : needsUsername ? (
              <Link to="/set-username?next=invitation" className="btn-primary flex w-full items-center justify-center">Finish setting up your account</Link>
            ) : !emailMatches ? (
              <div className="space-y-3">
                <p className="text-sm text-amber-800">You are signed in as {user.email}. Sign in with {invitation.recipient_email} to accept this invitation.</p>
                <button type="button" onClick={switchAccount} className="btn-primary w-full">Switch Google account</button>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="flex items-center gap-2 text-sm text-emerald-700"><CheckCircle2 className="h-4 w-4" />Signed in as the invited email address.</p>
                <button type="button" onClick={accept} disabled={accepting} className="btn-primary w-full disabled:cursor-not-allowed disabled:opacity-60">
                  {accepting ? 'Accepting invitation...' : 'Accept invitation'}
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
            <Link to="/" className="block text-center text-sm font-semibold underline">Return to CollabAI</Link>
          </div>
        )}
      </section>
    </main>
  )
}

export default InvitationLanding
