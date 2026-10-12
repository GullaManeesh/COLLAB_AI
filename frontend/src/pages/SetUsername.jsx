import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import api from '../api/client'
import { AtSign, ArrowRight, Layers, CheckCircle2 } from 'lucide-react'

const SetUsername = () => {
  const navigate = useNavigate()
  const { refreshUser } = useAuth()
  const [username, setUsername] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleUsernameChange = (e) => {
    // Sanitize: allow lowercase alphanumeric and underscores
    const val = e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '')
    setUsername(val)
    if (error) setError('')
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!username.trim()) {
      setError('Please enter a username.')
      return
    }
    if (username.length < 3) {
      setError('Username must be at least 3 characters long.')
      return
    }

    setLoading(true)
    setError('')
    try {
      await api.patch('/auth/username', { username })
      await refreshUser()
      navigate('/workspaces', { replace: true })
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not save username. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen w-full overflow-y-auto flex items-center justify-center bg-[#F8F8F6] px-4 py-8 sm:p-6 font-sans select-none selection:bg-zinc-200 selection:text-zinc-900">
      <div className="w-full max-w-md bg-white border border-[#E4E4E0] rounded-2xl p-6 sm:p-8 shadow-xl">
        {/* Header */}
        <div className="flex flex-col items-center text-center mb-8">
          <div className="w-12 h-12 rounded-2xl bg-[#18181B] text-white border border-[#18181B] flex items-center justify-center mb-3 shadow-xs">
            <Layers className="w-6 h-6" />
          </div>
          <h2 className="font-display font-bold text-2xl text-[#18181B] tracking-tight">Choose your username</h2>
          <p className="text-[#52525B] text-xs sm:text-sm mt-1.5 max-w-xs">
            Pick a handle for your team mentions, workspace activity, and profile.
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <label className="text-xs font-semibold text-[#18181B] flex items-center justify-between">
              <span>Username</span>
              <span className="text-[11px] font-normal text-[#71717A]">3-20 characters</span>
            </label>

            <div className="relative">
              <div className="absolute left-3.5 top-1/2 -translate-y-1/2 flex items-center pointer-events-none text-[#71717A]">
                <AtSign className="w-4 h-4" />
              </div>
              <input
                type="text"
                autoFocus
                maxLength={20}
                required
                value={username}
                onChange={handleUsernameChange}
                placeholder="yourhandle"
                className="w-full bg-[#F8F8F6] border border-[#E4E4E0] text-[#18181B] font-medium text-sm pl-10 pr-10 py-3 rounded-xl focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#18181B]/10 focus:border-[#18181B] transition-all placeholder:text-[#A1A1AA]"
              />
              {username.length >= 3 && (
                <div className="absolute right-3.5 top-1/2 -translate-y-1/2 text-emerald-600">
                  <CheckCircle2 className="w-4 h-4" />
                </div>
              )}
            </div>

            {error && (
              <p className="text-xs text-rose-600 font-medium mt-1">{error}</p>
            )}
          </div>

          <button
            type="submit"
            disabled={loading || !username}
            className="w-full flex items-center justify-center gap-2 bg-[#18181B] hover:bg-black text-white font-medium py-3 px-4 rounded-xl text-sm transition-all duration-150 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            {loading ? (
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <>
                <span>Continue to Workspaces</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>

        {/* Footer info */}
        <p className="text-center text-[11px] text-[#A1A1AA] mt-6">
          You can change your display name anytime inside Settings.
        </p>
      </div>
    </div>
  )
}

export default SetUsername
