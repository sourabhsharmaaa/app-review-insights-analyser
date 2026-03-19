// Central API base URL — uses VITE_API_BASE_URL in production, empty string locally (Vite proxy handles it)
const BASE = import.meta.env.VITE_API_BASE_URL || ''

export default BASE
