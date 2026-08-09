import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { recsApi } from '../api';
import { MovieRow } from '../components/movies/MovieRow';
import { MovieRowSkeleton, ErrorState } from '../components/movies/MovieCard';
import { useAuthStore } from '../store/auth';
import type { HomepageData } from '../types';
import { Sparkles, TrendingUp } from 'lucide-react';

export function HomePage() {
  const { user, isAuthenticated } = useAuthStore();

  const { data, isLoading, error, refetch } = useQuery<HomepageData>({
    queryKey: ['home'],
    queryFn: recsApi.getHome,
    enabled: isAuthenticated(),
    staleTime: 5 * 60 * 1000, // 5 min
    retry: 2,
  });

  if (!isAuthenticated()) {
    return <LandingPage />;
  }

  return (
    <div className="pt-14 min-h-screen">
      {/* Hero greeting */}
      <div className="px-4 sm:px-8 pt-8 pb-6">
        <div className="flex items-center gap-2 mb-1">
          <Sparkles size={16} className="text-brand-amber" />
          <span className="text-xs text-brand-amber font-medium uppercase tracking-wider">
            {data?.is_cold_start ? 'Getting to know you' : 'Personalized for you'}
          </span>
        </div>
        <h1 className="font-display text-2xl sm:text-3xl text-brand-text">
          Welcome back, <span className="text-brand-amber">{user?.username}</span>
        </h1>
        {data?.is_cold_start && (
          <p className="text-brand-muted text-sm mt-1">
            Recommendations improve as you watch and rate more movies.
          </p>
        )}
      </div>

      {/* Error state */}
      {error && !isLoading && (
        <div className="px-4 sm:px-8">
          <ErrorState
            message="Couldn't load recommendations. Showing popular titles instead."
            onRetry={refetch}
          />
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="space-y-10 px-0 py-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="px-4 sm:px-8">
              <MovieRowSkeleton />
            </div>
          ))}
        </div>
      )}

      {/* Sections */}
      {data && (
        <div className="space-y-10 pb-12">
          {data.sections
            .filter(s => s.items.length > 0)
            .map(section => (
              <MovieRow key={section.section_key} section={section} />
            ))}
        </div>
      )}
    </div>
  );
}

function LandingPage() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Hero */}
      <div className="relative flex-1 flex items-center justify-center overflow-hidden pt-14">
        {/* Background gradient */}
        <div className="absolute inset-0 bg-gradient-to-b from-brand-amber/5 via-transparent to-brand-bg" />

        <div className="relative text-center px-4 max-w-3xl mx-auto py-24">
          <div className="flex items-center justify-center gap-2 mb-6">
            <TrendingUp size={18} className="text-brand-amber" />
            <span className="text-brand-amber text-sm font-medium tracking-widest uppercase">
              AI-Powered Movie Discovery
            </span>
          </div>

          <h1 className="font-display text-5xl sm:text-7xl font-bold text-brand-text mb-6 leading-tight">
            Find your next<br />
            <span className="text-brand-amber">obsession</span>
          </h1>

          <p className="text-brand-muted text-lg sm:text-xl mb-10 leading-relaxed max-w-xl mx-auto">
            Cinemate learns from every click, rating, and reaction to surface films
            you'll genuinely love — not just what's trending.
          </p>

          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              to="/register"
              className="px-8 py-3.5 bg-brand-amber text-black font-semibold rounded-xl hover:bg-brand-amber-dim transition-colors text-base"
            >
              Start discovering
            </Link>
            <Link
              to="/login"
              className="px-8 py-3.5 bg-brand-surface border border-brand-border text-brand-text font-medium rounded-xl hover:border-brand-amber transition-colors text-base"
            >
              Sign in
            </Link>
          </div>

          {/* Feature pills */}
          <div className="flex flex-wrap justify-center gap-2 mt-12">
            {[
              'Collaborative Filtering',
              'Neural Recommender',
              'Semantic Search',
              '5,000+ Movies',
              'Live Re-ranking',
              'Explainable AI',
            ].map(f => (
              <span key={f} className="text-xs text-brand-muted border border-brand-border px-3 py-1 rounded-full">
                {f}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}


