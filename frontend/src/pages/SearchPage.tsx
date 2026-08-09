
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Search, Sparkles, AlertCircle } from 'lucide-react';
import { searchApi } from '../api';
import { MovieCard } from '../components/movies/MovieCard';
import { MovieCardSkeleton, EmptyState } from '../components/movies/MovieCard';
import type { MovieCard as MovieCardType } from '../types';

export function SearchPage() {
  const [params] = useSearchParams();
  const q = params.get('q') || '';

  const { data, isLoading, error } = useQuery({
    queryKey: ['search', q],
    queryFn: () => searchApi.search(q),
    enabled: q.length > 0,
    staleTime: 60 * 1000,
  });

  if (!q) {
    return (
      <div className="pt-24 px-4 max-w-4xl mx-auto">
        <EmptyState message="Enter a search term to find movies." />
      </div>
    );
  }

  return (
    <div className="pt-20 pb-16 px-4 sm:px-8 max-w-7xl mx-auto">
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-1">
          <Search size={16} className="text-brand-muted" />
          <span className="text-brand-muted text-sm">Search results for</span>
        </div>
        <h1 className="font-display text-2xl sm:text-3xl font-bold text-brand-text">
          "{q}"
        </h1>
        {data && (
          <p className="text-brand-muted text-sm mt-1">
            {data.total} result{data.total !== 1 ? 's' : ''}
            {data.semantic_used && (
              <span className="ml-2 inline-flex items-center gap-1 text-brand-amber">
                <Sparkles size={12} /> Semantic search active
              </span>
            )}
          </p>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-2 text-red-400 bg-red-400/10 rounded-xl px-4 py-3 mb-6">
          <AlertCircle size={16} />
          Search failed. Please try again.
        </div>
      )}

      {isLoading && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
          {Array.from({ length: 12 }).map((_, i) => <MovieCardSkeleton key={i} />)}
        </div>
      )}

      {data?.movies.length === 0 && !isLoading && (
        <EmptyState
          message={`No movies found for "${q}". Try different keywords.`}
        />
      )}

      {data?.movies && data.movies.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
          {data.movies.map((movie: MovieCardType) => (
            <MovieCard key={movie.id} movie={movie} />
          ))}
        </div>
      )}
    </div>
  );
}
