
import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { GoogleLogin } from '@react-oauth/google'
import { Layers } from 'lucide-react'
import api from '../api/client'

const Login = () => {
  const navigate = useNavigate()
  const { refreshUser } = useAuth()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleGoogleSuccess = async (googleResponse) => {
    if (!googleResponse.credential) {
      setError('Google did not return an ID token. Please try again.')
      return
    }

    setLoading(true)
    setError('')

    try {
      // This endpoint must verify Google, find/create the user,
      // and issue a secure HttpOnly session cookie.
      const response = await api.post('/auth/google', {
        credential: googleResponse.credential,
      })

      const { user, needs_username } = response.data
      await refreshUser()

      if (!user) {
        throw new Error('The server did not return a user.')
      }

      if (needs_username || !user.username) {
        navigate('/set-username', { replace: true })
      } else {
        navigate('/workspaces', { replace: true })
      }
    } catch (err) {
      if (err.response) {
        setError(
          err.response.data?.detail || 'Google sign-in failed. Please try again.',
        )
      } else if (err.code === 'ECONNABORTED') {
        setError('The request timed out. Please try again.')
      } else {
        setError('Cannot reach CollabAI. Check that the backend is running.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen w-full overflow-y-auto flex items-center justify-center bg-[#F8F8F6] px-4 py-8 sm:p-6 font-sans selection:bg-zinc-200 selection:text-zinc-900">
      <div className="w-full max-w-md bg-white border border-[#E4E4E0] rounded-2xl p-6 sm:p-8 shadow-xl">
        <div className="flex flex-col items-center mb-8 text-center">
          <div className="w-12 h-12 rounded-2xl bg-[#18181B] text-white border border-[#18181B] flex items-center justify-center mb-3 shadow-xs">
            <Layers className="w-6 h-6" />
          </div>

          <h2 className="font-display font-bold text-2xl text-[#18181B] tracking-tight">
            Welcome to CollabAI
          </h2>

          <p className="text-[#52525B] text-xs sm:text-sm mt-1.5 max-w-xs">
            Sign in to access your intelligent team workspaces and AI teammates
          </p>
        </div>

        <div className="flex flex-col items-center gap-4">
          {loading ? (
            <div
              className="w-5 h-5 border-2 border-[#18181B] border-t-transparent rounded-full animate-spin"
              role="status"
              aria-label="Signing in"
            />
          ) : (
            <div className="w-[320px] max-w-full flex justify-center items-center rounded-full transition-all duration-200 hover:shadow-sm">
              <GoogleLogin
                onSuccess={handleGoogleSuccess}
                onError={() => setError('Google sign-in was cancelled or failed.')}
                text="continue_with"
                theme="outline"
                shape="pill"
                size="large"
                width="320"
                useOneTap={false}
              />
            </div>
          )}

          {error && (
            <p role="alert" className="text-sm text-red-600 text-center">
              {error}
            </p>
          )}
        </div>

        <div className="mt-8 pt-6 border-t border-[#F0F0EE] text-center text-[11px] text-[#71717A] leading-relaxed">
          By signing in, you agree to our{' '}
          <span className="text-[#18181B] hover:underline cursor-pointer">
            Terms of Service
          </span>{' '}
          and{' '}
          <span className="text-[#18181B] hover:underline cursor-pointer">
            Privacy Policy
          </span>.
        </div>
      </div>
    </div>
  )
}

export default Login



