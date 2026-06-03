import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ProtectedRoute } from './components/ProtectedRoute'
import { RoleRedirect } from './components/RoleRedirect'

const LandingPage = lazy(() => import('./pages/LandingPage').then((module) => ({ default: module.LandingPage })))
const LoginPage = lazy(() => import('./pages/LoginPage').then((module) => ({ default: module.LoginPage })))
const ForgotPasswordPage = lazy(() => import('./pages/ForgotPasswordPage').then((module) => ({ default: module.ForgotPasswordPage })))
const ResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage').then((module) => ({ default: module.ResetPasswordPage })))
const OwnerLockPage = lazy(() => import('./pages/OwnerLockPage').then((module) => ({ default: module.OwnerLockPage })))
const ChatPage = lazy(() => import('./pages/ChatPage').then((module) => ({ default: module.ChatPage })))
const AdminPage = lazy(() => import('./pages/AdminPage').then((module) => ({ default: module.AdminPage })))
const ApiDocsPage = lazy(() => import('./pages/ApiDocsPage').then((module) => ({ default: module.ApiDocsPage })))

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/owner-lock" element={<OwnerLockPage />} />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <RoleRedirect />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin"
            element={
              <ProtectedRoute requireAdmin>
                <AdminPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/scalar"
            element={
              <ProtectedRoute requireAdmin>
                <ApiDocsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/chat"
            element={
              <ProtectedRoute>
                <ChatPage />
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}

function RouteFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background text-sm text-muted-foreground">
      Loading...
    </div>
  )
}
