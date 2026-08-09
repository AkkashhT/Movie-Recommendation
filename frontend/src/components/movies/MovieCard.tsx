import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Star, Plus, Check, Info } from 'lucide-react';
import { posterUrl } from '../../api/client';
import type { MovieCard as MovieCardType } from '../../types';
import { interactionsApi } from '../../api';
import { useAuthStore } from '../../store/auth';

interface Props {
  movie: MovieCardType;
  explanation?: string;
  showExplanation?: boolean;
  onInteraction?: () => void;
}

export function MovieCard({ movie, explanation, showExplanation, onInteraction }: Props) {
  const [hovered, setHovered] = useState(false);
  const [inWatchlist, setInWatchlist] = useState(false);
  const { isAuthenticated } = useAuthStore();

  const handleClick = () => {
    if (isAuthenticated()) {
      interactionsApi.log(movie.id, 'CLICK').catch(() => {});
    }
  };

  const handleWatchlist = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isAuthenticated()) return;
    const type = inWatchlist ? 'WISHLIST_REMOVE' : 'WISHLIST_ADD';
    await interactionsApi.log(movie.id, type);
    setInWatchlist(!inWatchlist);
    onInteraction?.();
  };

  const year = movie.release_date ? new Date(movie.release_date).getFullYear() : null;
  const rating = movie.vote_average ? movie.vote_average.toFixed(1) : null;

  return (
    <Link
      to={`/movie/${movie.id}`}
      onClick={handleClick}
      className="group relative block flex-shrink-0 w-36 sm:w-44"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Poster */}
      <div className="relative rounded-lg overflow-hidden bg-brand-card aspect-[2/3]">
        {movie.poster_path ? (
          <img
            src={posterUrl(movie.poster_path)}
            alt={movie.title}
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-brand-card">
            <Info size={32} className="text-brand-muted" />
          </div>
        )}

        {/* Overlay on hover */}
        <div className={`absolute inset-0 bg-black/70 flex flex-col justify-between p-2 transition-opacity duration-200 ${hovered ? 'opacity-100' : 'opacity-0'}`}>
          {/* Rating badge */}
          {rating && (
            <div className="flex items-center gap-1 self-end bg-black/60 rounded px-1.5 py-0.5">
              <Star size={10} className="text-brand-amber fill-brand-amber" />
              <span className="text-xs text-brand-amber font-medium">{rating}</span>
            </div>
          )}

          {/* Watchlist button */}
          <button
            onClick={handleWatchlist}
            className="self-end bg-brand-amber hover:bg-brand-amber-dim text-black rounded-full p-1 transition-colors"
            title={inWatchlist ? 'Remove from watchlist' : 'Add to watchlist'}
          >
            {inWatchlist ? <Check size={14} /> : <Plus size={14} />}
          </button>
        </div>
      </div>

      {/* Title + Year */}
      <div className="mt-1.5 px-0.5">
        <p className="text-xs font-medium text-brand-text leading-tight line-clamp-2 group-hover:text-brand-amber transition-colors">
          {movie.title}
        </p>
        {year && <p className="text-xs text-brand-muted mt-0.5">{year}</p>}
      </div>

      {/* Explanation tooltip */}
      {showExplanation && explanation && hovered && (
        <div className="absolute bottom-full left-0 mb-2 w-48 bg-brand-surface border border-brand-border rounded-lg p-2 text-xs text-brand-muted z-50 shadow-xl">
          {explanation}
        </div>
      )}
    </Link>
  );
}

// ── Loading skeletons ─────────────────────────────────────────
export function MovieCardSkeleton() {
  return (
    <div className="flex-shrink-0 w-36 sm:w-44 animate-pulse">
      <div className="rounded-lg bg-brand-card aspect-[2/3]" />
      <div className="mt-1.5 space-y-1">
        <div className="h-3 bg-brand-card rounded w-3/4" />
        <div className="h-2.5 bg-brand-card rounded w-1/3" />
      </div>
    </div>
  );
}

export function MovieRowSkeleton() {
  return (
    <div className="space-y-3">
      <div className="h-5 w-48 bg-brand-card rounded animate-pulse" />
      <div className="flex gap-3">
        {Array.from({ length: 7 }).map((_, i) => <MovieCardSkeleton key={i} />)}
      </div>
    </div>
  );
}

// ── Error state ───────────────────────────────────────────────
export function ErrorState({ message, onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="text-brand-muted text-4xl mb-3">⚠️</div>
      <p className="text-brand-muted text-sm mb-4">{message || 'Something went wrong.'}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="px-4 py-2 bg-brand-amber text-black text-sm font-medium rounded-lg hover:bg-brand-amber-dim transition-colors"
        >
          Try again
        </button>
      )}
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────
export function EmptyState({ message, action }: { message: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center gap-4">
      <div className="text-6xl">🎬</div>
      <p className="text-brand-muted">{message}</p>
      {action}
    </div>
  );
}
