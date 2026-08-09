import { api } from './client';

// ── Auth ──────────────────────────────────────────────────────
export const authApi = {
  register: (data: { email: string; username: string; password: string; full_name?: string }) =>
    api.post('/auth/register', data).then(r => r.data),

  login: (email: string, password: string) =>
    api.post('/auth/login', { email, password }).then(r => r.data),

  refresh: (token: string) =>
    api.post('/auth/refresh', { refresh_token: token }).then(r => r.data),

  me: () => api.get('/auth/me').then(r => r.data),
};

// ── Users / Onboarding ───────────────────────────────────────
export const usersApi = {
  getGenres: () => api.get('/users/genres').then(r => r.data),

  searchPersons: (q: string) =>
    api.get('/users/search/persons', { params: { q } }).then(r => r.data),

  completeOnboarding: (data: { genre_ids: number[]; actor_ids: number[]; director_ids: number[] }) =>
    api.post('/users/onboarding', data).then(r => r.data),

  getPreferences: () => api.get('/users/preferences').then(r => r.data),
  updatePreferences: (data: { genre_ids: number[]; actor_ids: number[]; director_ids: number[] }) =>
    api.put('/users/preferences', data).then(r => r.data),

  getWatchlist: (page = 1) =>
    api.get('/users/watchlist', { params: { page } }).then(r => r.data),
};

// ── Movies ───────────────────────────────────────────────────
export const moviesApi = {
  getMovie: (id: number) => api.get(`/movies/${id}`).then(r => r.data),
  getSimilar: (id: number, limit = 12) =>
    api.get(`/movies/${id}/similar`, { params: { limit } }).then(r => r.data),
  getExplanation: (id: number) =>
    api.get(`/movies/${id}/explanation`).then(r => r.data),
};

// ── Interactions ─────────────────────────────────────────────
export const interactionsApi = {
  log: (movie_id: number, type: string, metadata?: Record<string, unknown>) =>
    api.post('/interactions', { movie_id, type, metadata }).then(r => r.data),
};

// ── Recommendations ──────────────────────────────────────────
export const recsApi = {
  getHome: () => api.get('/recommendations/home').then(r => r.data),
  getForYou: (limit = 20) =>
    api.get('/recommendations/for-you', { params: { limit } }).then(r => r.data),
};

// ── Search ───────────────────────────────────────────────────
export const searchApi = {
  search: (q: string, page = 1) =>
    api.get('/search', { params: { q, page } }).then(r => r.data),
  autocomplete: (q: string) =>
    api.get('/search/autocomplete', { params: { q } }).then(r => r.data),
};

// ── Admin ─────────────────────────────────────────────────────
export const adminApi = {
  getDashboard: () => api.get('/admin/dashboard').then(r => r.data),
  triggerTraining: () => api.post('/admin/ml/ingest-and-train').then(r => r.data),
  getTrainingStatus: () => api.get('/admin/ml/training-status').then(r => r.data),
  runEvaluation: () => api.get('/admin/ml/evaluation').then(r => r.data),
};
