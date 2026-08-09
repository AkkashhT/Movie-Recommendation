import { useQuery } from '@tanstack/react-query';
import { Bookmark } from 'lucide-react';
import { usersApi } from '../api';
import { MovieCard } from '../components/movies/MovieCard';
import { MovieCardSkeleton, EmptyState, ErrorState } from '../components/movies/MovieCard';
import { Link } from 'react-router-dom';

export function WatchlistPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['watchlist'],
    queryFn: () => usersApi.getWatchlist(),
    staleTime: 60 * 1000,
  });

  return (
    <div className="pt-20 pb-16 px-4 sm:px-8 max-w-7xl mx-auto">
      <div className="flex items-center gap-3 mb-8">
        <Bookmark size={22} className="text-brand-amber" />
        <h1 className="font-display text-2xl sm:text-3xl font-bold text-brand-text">My Watchlist</h1>
        {data?.items && (
          <span className="text-sm text-brand-muted">({data.items.length} movies)</span>
        )}
      </div>

      {error && <ErrorState message="Couldn't load watchlist." onRetry={refetch} />}

      {isLoading && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
          {Array.from({ length: 8 }).map((_, i) => <MovieCardSkeleton key={i} />)}
        </div>
      )}

      {data?.items?.length === 0 && (
        <EmptyState
          message="Your watchlist is empty. Add movies to watch later."
          action={
            <Link to="/"
              className="px-4 py-2 bg-brand-amber text-black text-sm font-medium rounded-lg hover:bg-brand-amber-dim transition-colors">
              Browse movies
            </Link>
          }
        />
      )}

      {data?.items && data.items.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
          {data.items.map((item: any) => (
            <MovieCard key={item.movie.id} movie={item.movie} />
          ))}
        </div>
      )}
    </div>
  );
}
