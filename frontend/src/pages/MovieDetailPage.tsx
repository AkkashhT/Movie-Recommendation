import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Star, Clock, Plus, Check, ThumbsUp, ThumbsDown,
  Play, Info, Lightbulb, BarChart2
} from 'lucide-react';
import { moviesApi, interactionsApi } from '../api';
import { posterUrl, backdropUrl } from '../api/client';
import { MovieCard, ErrorState } from '../components/movies/MovieCard';
import { useAuthStore } from '../store/auth';
import type { MovieDetail } from '../types';

export function MovieDetailPage() {
  const { id } = useParams<{ id: string }>();
  const movieId = parseInt(id!);
  const { isAuthenticated } = useAuthStore();
  const qc = useQueryClient();

  const { data: movie, isLoading, error, refetch } = useQuery<MovieDetail>({
    queryKey: ['movie', movieId],
    queryFn: () => moviesApi.getMovie(movieId),
    staleTime: 10 * 60 * 1000,
  });

  const { data: similar } = useQuery({
    queryKey: ['similar', movieId],
    queryFn: () => moviesApi.getSimilar(movieId, 12),
    enabled: !!movie,
  });

  const { data: explanation } = useQuery({
    queryKey: ['explanation', movieId],
    queryFn: () => moviesApi.getExplanation(movieId),
    enabled: !!movie && isAuthenticated(),
  });

  // Log VIEW on mount
  useEffect(() => {
    if (movie && isAuthenticated()) {
      interactionsApi.log(movieId, 'VIEW').catch(() => {});
    }
  }, [movieId, movie]);

  const [inWatchlist, setInWatchlist] = useState<boolean | null>(null);
  const [liked, setLiked] = useState<boolean | null>(null);
  const [userRating, setUserRating] = useState<number | null>(null);
  const [showTrailer, setShowTrailer] = useState(false);
  const [showScores, setShowScores] = useState(false);

  useEffect(() => {
    if (movie) {
      setInWatchlist(movie.in_watchlist ?? false);
      setLiked(movie.user_liked ?? null);
      setUserRating(movie.user_rating ?? null);
    }
  }, [movie]);

  const handleWatchlist = async () => {
    if (!isAuthenticated()) return;
    const type = inWatchlist ? 'WISHLIST_REMOVE' : 'WISHLIST_ADD';
    await interactionsApi.log(movieId, type);
    setInWatchlist(!inWatchlist);
    qc.invalidateQueries({ queryKey: ['home'] });
  };

  const handleLike = async (like: boolean) => {
    if (!isAuthenticated()) return;
    const newLiked = liked === like ? null : like;
    if (newLiked !== null) {
      await interactionsApi.log(movieId, newLiked ? 'LIKE' : 'DISLIKE');
    }
    setLiked(newLiked);
    qc.invalidateQueries({ queryKey: ['home'] });
  };

  const handleRate = async (rating: number) => {
    if (!isAuthenticated()) return;
    await interactionsApi.log(movieId, 'RATE', { rating });
    setUserRating(rating);
    qc.invalidateQueries({ queryKey: ['home'] });
  };

  if (isLoading) return <DetailSkeleton />;
  if (error || !movie) return (
    <div className="pt-24 px-4 max-w-4xl mx-auto">
      <ErrorState message="Movie not found." onRetry={refetch} />
    </div>
  );

  const directors = movie.directors || [];
  const leadCast = movie.cast?.filter(c => c.is_lead) || [];
  const supportCast = movie.cast?.filter(c => !c.is_lead).slice(0, 8) || [];
  const year = movie.release_date ? new Date(movie.release_date).getFullYear() : null;
  const backdrop = backdropUrl(movie.backdrop_path);

  return (
    <div className="min-h-screen pt-14">
      {/* Backdrop hero */}
      <div className="relative h-72 sm:h-96 overflow-hidden">
        {backdrop ? (
          <img src={backdrop} alt="" className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full bg-brand-surface" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-brand-bg via-brand-bg/60 to-transparent" />
      </div>

      {/* Main content — overlaps backdrop */}
      <div className="relative -mt-32 sm:-mt-48 px-4 sm:px-8 max-w-6xl mx-auto pb-16">
        <div className="flex flex-col sm:flex-row gap-6">
          {/* Poster */}
          <div className="flex-shrink-0 self-start">
            <div className="w-40 sm:w-56 rounded-xl overflow-hidden shadow-2xl border border-brand-border">
              {movie.poster_path ? (
                <img src={posterUrl(movie.poster_path, 'w342')} alt={movie.title}
                  className="w-full aspect-[2/3] object-cover" />
              ) : (
                <div className="w-full aspect-[2/3] bg-brand-card flex items-center justify-center">
                  <Info size={40} className="text-brand-muted" />
                </div>
              )}
            </div>
          </div>

          {/* Info */}
          <div className="flex-1 space-y-4 pt-32 sm:pt-0">
            {/* Title */}
            <div>
              <h1 className="font-display text-3xl sm:text-4xl font-bold text-brand-text leading-tight">
                {movie.title}
              </h1>
              {movie.tagline && (
                <p className="text-brand-muted italic mt-1">"{movie.tagline}"</p>
              )}
            </div>

            {/* Meta row */}
            <div className="flex flex-wrap items-center gap-3 text-sm text-brand-muted">
              {year && <span>{year}</span>}
              {movie.runtime && (
                <span className="flex items-center gap-1">
                  <Clock size={13} /> {movie.runtime} min
                </span>
              )}
              {movie.vote_average && (
                <span className="flex items-center gap-1 text-brand-amber font-medium">
                  <Star size={13} className="fill-brand-amber" />
                  {Number(movie.vote_average).toFixed(1)}
                  <span className="text-brand-muted font-normal">({movie.vote_count?.toLocaleString()})</span>
                </span>
              )}
              {movie.language && movie.language !== 'en' && (
                <span className="uppercase border border-brand-border rounded px-1.5 py-0.5 text-xs">
                  {movie.language}
                </span>
              )}
            </div>

            {/* Genres */}
            <div className="flex flex-wrap gap-2">
              {movie.genres.map(g => (
                <span key={g.id} className="text-xs px-3 py-1 bg-brand-card border border-brand-border rounded-full text-brand-muted">
                  {g.name}
                </span>
              ))}
            </div>

            {/* Action buttons */}
            {isAuthenticated() && (
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <button onClick={handleWatchlist}
                  className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${inWatchlist ? 'bg-brand-amber text-black' : 'bg-brand-surface border border-brand-border text-brand-text hover:border-brand-amber'}`}>
                  {inWatchlist ? <Check size={15} /> : <Plus size={15} />}
                  {inWatchlist ? 'In Watchlist' : 'Add to Watchlist'}
                </button>

                <button onClick={() => handleLike(true)}
                  className={`p-2 rounded-xl transition-all border ${liked === true ? 'bg-green-500/20 border-green-500 text-green-400' : 'border-brand-border text-brand-muted hover:border-green-500'}`}>
                  <ThumbsUp size={16} />
                </button>

                <button onClick={() => handleLike(false)}
                  className={`p-2 rounded-xl transition-all border ${liked === false ? 'bg-red-500/20 border-red-500 text-red-400' : 'border-brand-border text-brand-muted hover:border-red-500'}`}>
                  <ThumbsDown size={16} />
                </button>

                {movie.trailer_key && (
                  <button onClick={() => setShowTrailer(true)}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium bg-brand-surface border border-brand-border text-brand-text hover:border-brand-amber transition-all">
                    <Play size={15} className="text-brand-amber" /> Watch Trailer
                  </button>
                )}
              </div>
            )}

            {/* Star rating */}
            {isAuthenticated() && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-brand-muted">Your rating:</span>
                <div className="flex gap-0.5">
                  {[1,2,3,4,5,6,7,8,9,10].map(n => (
                    <button key={n} onClick={() => handleRate(n)}
                      className={`text-lg transition-colors ${userRating && n <= userRating ? 'text-brand-amber' : 'text-brand-border hover:text-brand-amber'}`}>
                      ★
                    </button>
                  ))}
                </div>
                {userRating && <span className="text-xs text-brand-amber">{userRating}/10</span>}
              </div>
            )}
          </div>
        </div>

        {/* Overview */}
        {movie.overview && (
          <div className="mt-8 max-w-3xl">
            <h2 className="font-display text-xl font-semibold text-brand-text mb-2">Overview</h2>
            <p className="text-brand-muted leading-relaxed">{movie.overview}</p>
          </div>
        )}

        {/* Directors + Lead Cast */}
        <div className="mt-8 grid sm:grid-cols-2 gap-8">
          {directors.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-brand-muted uppercase tracking-wider mb-3">
                {directors.length > 1 ? 'Directors' : 'Director'}
              </h3>
              <div className="space-y-2">
                {directors.map((d: any) => (
                  <div key={d.id} className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-brand-card flex items-center justify-center text-xs text-brand-muted">
                      {d.name[0]}
                    </div>
                    <span className="text-sm text-brand-text">{d.name}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {leadCast.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-brand-muted uppercase tracking-wider mb-3">Stars</h3>
              <div className="space-y-2">
                {leadCast.map((c: any) => (
                  <div key={c.person.id} className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-brand-card flex items-center justify-center text-xs text-brand-muted">
                      {c.person.name[0]}
                    </div>
                    <div>
                      <p className="text-sm text-brand-text">{c.person.name}</p>
                      {c.character && <p className="text-xs text-brand-muted">{c.character}</p>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Supporting cast */}
        {supportCast.length > 0 && (
          <div className="mt-6">
            <h3 className="text-sm font-medium text-brand-muted uppercase tracking-wider mb-3">Also Featuring</h3>
            <div className="flex flex-wrap gap-2">
              {supportCast.map((c: any) => (
                <span key={c.person.id} className="text-xs text-brand-muted border border-brand-border rounded-full px-3 py-1">
                  {c.person.name}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Keywords */}
        {movie.keywords && movie.keywords.length > 0 && (
          <div className="mt-6">
            <h3 className="text-sm font-medium text-brand-muted uppercase tracking-wider mb-3">Keywords</h3>
            <div className="flex flex-wrap gap-2">
              {movie.keywords.slice(0, 15).map((kw: string) => (
                <span key={kw} className="text-xs text-brand-muted bg-brand-card rounded px-2 py-0.5">{kw}</span>
              ))}
            </div>
          </div>
        )}

        {/* AI Explanation panel */}
        {explanation && (
          <div className="mt-8 bg-brand-surface border border-brand-border rounded-2xl p-5 max-w-2xl">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Lightbulb size={16} className="text-brand-amber" />
                <h3 className="text-sm font-semibold text-brand-text">Why this was recommended</h3>
              </div>
              <button onClick={() => setShowScores(!showScores)}
                className="flex items-center gap-1 text-xs text-brand-muted hover:text-brand-amber transition-colors">
                <BarChart2 size={13} /> {showScores ? 'Hide' : 'Show'} scores
              </button>
            </div>
            <p className="text-brand-muted text-sm">{explanation.explanation}</p>

            {showScores && explanation.scores && (
              <div className="mt-4 space-y-2">
                {Object.entries(explanation.scores).map(([key, val]: any) => val != null && (
                  <div key={key} className="flex items-center gap-3">
                    <span className="text-xs text-brand-muted w-24 capitalize">{key.replace('_', ' ')}</span>
                    <div className="flex-1 h-1.5 bg-brand-card rounded-full overflow-hidden">
                      <div className="h-full bg-brand-amber rounded-full transition-all"
                        style={{ width: `${Math.round(val * 100)}%` }} />
                    </div>
                    <span className="text-xs text-brand-muted w-8 text-right">{(val * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Similar movies */}
        {similar && similar.length > 0 && (
          <div className="mt-12">
            <h2 className="font-display text-xl font-semibold text-brand-text mb-4 px-0">
              More Like This
            </h2>
            <div className="flex gap-3 overflow-x-auto scrollbar-hide pb-2">
              {similar.map((m: any) => (
                <MovieCard key={m.id} movie={m} />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Trailer modal */}
      {showTrailer && movie.trailer_key && (
        <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
          onClick={() => setShowTrailer(false)}>
          <div className="relative w-full max-w-4xl aspect-video" onClick={e => e.stopPropagation()}>
            <iframe
              src={`https://www.youtube.com/embed/${movie.trailer_key}?autoplay=1`}
              className="w-full h-full rounded-xl"
              allow="autoplay; fullscreen"
              allowFullScreen
            />
            <button onClick={() => setShowTrailer(false)}
              className="absolute -top-10 right-0 text-white/70 hover:text-white text-sm">
              ✕ Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="min-h-screen pt-14 animate-pulse">
      <div className="h-72 sm:h-96 bg-brand-surface" />
      <div className="relative -mt-32 px-4 sm:px-8 max-w-6xl mx-auto pb-16">
        <div className="flex gap-6">
          <div className="w-40 sm:w-56 aspect-[2/3] bg-brand-card rounded-xl flex-shrink-0" />
          <div className="flex-1 pt-32 sm:pt-0 space-y-4">
            <div className="h-8 bg-brand-card rounded w-3/4" />
            <div className="h-4 bg-brand-card rounded w-1/2" />
            <div className="flex gap-2">
              {[1,2,3].map(i => <div key={i} className="h-6 w-16 bg-brand-card rounded-full" />)}
            </div>
          </div>
        </div>
        <div className="mt-8 space-y-2 max-w-3xl">
          {[1,2,3,4].map(i => <div key={i} className="h-4 bg-brand-card rounded" />)}
        </div>
      </div>
    </div>
  );
}
