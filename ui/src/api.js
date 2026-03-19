// Central API base URL — uses VITE_API_BASE_URL in production, empty string locally (Vite proxy handles it)
// Strip trailing slash to avoid double-slash in URLs
const BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export default BASE
