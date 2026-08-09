import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Navbar } from './components/layout/Navbar';
import { HomePage } from './pages/HomePage';
import { LoginPage, RegisterPage } from './pages/AuthPages';
import { OnboardingPage } from './pages/OnboardingPage';
import { MovieDetailPage } from './pages/MovieDetailPage';
import { SearchPage } from './pages/SearchPage';
import { WatchlistPage } from './pages/WatchlistPage';
import { PreferencesPage } from './pages/PreferencesPage';
import { AdminDashboard } from './pages/AdminDashboard';
import { useAuthStore } from './store/auth';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, user } = useAuthStore();
  if (!isAuthenticated()) return <Navigate to="/login" replace />;
  if (!user?.onboarding_done) return <Navigate to="/onboarding" replace />;
  return <>{children}</>;
}

function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { isAdmin, isAuthenticated } = useAuthStore();
  if (!isAuthenticated()) return <Navigate to="/login" replace />;
  if (!isAdmin()) return <Navigate to="/" replace />;
  return <>{children}</>;
}

function RequireOnboarding({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore();
  if (!isAuthenticated()) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Navbar />
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/movie/:id" element={<MovieDetailPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/onboarding" element={<RequireOnboarding><OnboardingPage /></RequireOnboarding>} />
          <Route path="/watchlist" element={<RequireAuth><WatchlistPage /></RequireAuth>} />
          <Route path="/preferences" element={<RequireAuth><PreferencesPage /></RequireAuth>} />
          <Route path="/admin" element={<RequireAdmin><AdminDashboard /></RequireAdmin>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
