import axios from 'axios'

// In-memory CSRF token storage (cross-origin cookies can't be read via document.cookie)
let csrfToken = null

export function setCsrfToken(token) {
    csrfToken = token
}

export function getCsrfToken() {
    return csrfToken
}

const api = axios.create({
    baseURL: import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000',
    headers: {
        'Content-Type': 'application/json',
    },
    timeout: 300000,
    withCredentials: true,
})

api.interceptors.request.use((config) => {
    config.withCredentials = true
    if (csrfToken && ['post', 'put', 'patch', 'delete'].includes(config.method?.toLowerCase())) {
        config.headers['X-CSRF-Token'] = csrfToken
    }
    return config
})

api.interceptors.response.use(
    (response) => {
        // Auto-capture CSRF token from any auth response
        if (response.data?.csrf_token) {
            csrfToken = response.data.csrf_token
        }
        return response
    },
    (error) => {
        const requestUrl = error.config?.url || ''
        const isAuthEndpoint = requestUrl.startsWith('/auth/')
        const isUnauthorized = error.response?.status === 401
        const isPublicPage = ['/login', '/register', '/signup'].includes(window.location.pathname)

        if (isUnauthorized && !isAuthEndpoint && !isPublicPage) {
            window.location.assign('/login')
        }

        return Promise.reject(error)
    },
)

export default api
