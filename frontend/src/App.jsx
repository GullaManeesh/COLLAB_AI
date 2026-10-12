import React from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import WorkspaceLayout from './components/layout/WorkspaceLayout'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Register from './pages/Register'
import SetUsername from './pages/SetUsername'
import Workspaces from './pages/Workspaces'
import Chat from './pages/Chat'
import Copilot from './pages/Copilot'
import Documents from './pages/Documents'
import Tasks from './pages/Tasks'
import Settings from './pages/Settings'
import Notifications from './pages/Notifications'
import './styles/index.css'

const RestoringSession = () => (
  <div className="flex min-h-screen items-center justify-center bg-[#F8F8F6] text-sm text-[#71717A]">
    Restoring session...
  </div>
)

const ProtectedRoute = ({ children }) => {
  const { user, loading, needsUsername } = useAuth()
  if (loading) return <RestoringSession />
  if (!user) return <Navigate to="/login" replace />
  if (needsUsername) return <Navigate to="/set-username" replace />
  return children
}

const UsernameRoute = () => {
  const { user, loading } = useAuth()
  if (loading) return <RestoringSession />
  return user ? <SetUsername /> : <Navigate to="/login" replace />
}

const HomeRoute = () => {
  const { user, loading } = useAuth()
  if (loading) return <RestoringSession />
  return user ? <Navigate to="/workspaces" replace /> : <Landing />
}

const WorkspaceRedirect = () => <Navigate to="chat" replace />

const App = () => (
  <AuthProvider>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomeRoute />} />
        <Route path="/login" element={<Login />} />
        <Route path="/set-username" element={<UsernameRoute />} />
        <Route path="/username" element={<UsernameRoute />} />
        <Route path="/register" element={<Register />} />
        <Route path="/signup" element={<Register />} />
        <Route path="/workspaces" element={<ProtectedRoute><Workspaces /></ProtectedRoute>} />
        <Route path="/notifications" element={<ProtectedRoute><Notifications /></ProtectedRoute>} />
        <Route path="/w/:id" element={<ProtectedRoute><WorkspaceLayout /></ProtectedRoute>}>
          <Route index element={<WorkspaceRedirect />} />
          <Route path="chat" element={<Chat />} />
          <Route path="copilot" element={<Copilot />} />
          <Route path="docs" element={<Documents />} />
          <Route path="tasks" element={<Tasks />} />
          <Route path="settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  </AuthProvider>
)

export default App
