import axios from 'axios'

const csrfCookieName = import.meta.env.VITE_CSRF_COOKIE_NAME || 'collabai_csrf'

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
    const csrfToken = document.cookie
        .split('; ')
        .find((cookie) => cookie.startsWith(`${csrfCookieName}=`))
        ?.split('=')[1]
    if (csrfToken && ['post', 'put', 'patch', 'delete'].includes(config.method?.toLowerCase())) {
        config.headers['X-CSRF-Token'] = decodeURIComponent(csrfToken)
    }
    return config
})

api.interceptors.response.use(
    (response) => response,
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
