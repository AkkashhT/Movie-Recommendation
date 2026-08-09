import { useRef } from 'react';
import { ChevronLeft, ChevronRight, Lightbulb } from 'lucide-react';
import { MovieCard, MovieRowSkeleton } from './MovieCard';
import type { RecommendedMovie, HomeSection } from '../../types';

interface Props {
  section: HomeSection;
  isLoading?: boolean;
}

export function MovieRow({ section, isLoading }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const scroll = (dir: 'left' | 'right') => {
    if (!scrollRef.current) return;
    const amount = scrollRef.current.clientWidth * 0.75;
    scrollRef.current.scrollBy({ left: dir === 'right' ? amount : -amount, behavior: 'smooth' });
  };

  if (isLoading) return <MovieRowSkeleton />;
  if (!section.items.length) return null;

  return (
    <section className="space-y-3">
      {/* Section header */}
      <div className="flex items-center gap-3 px-4 sm:px-8">
        <h2 className="font-display text-lg sm:text-xl text-brand-text font-semibold">
          {section.title}
        </h2>
        {section.section_key === 'hidden_gems' && (
          <span className="flex items-center gap-1 text-xs text-brand-amber bg-brand-amber/10 px-2 py-0.5 rounded-full">
            <Lightbulb size={10} />
            Underrated
          </span>
        )}
      </div>

      {/* Scrollable row */}
      <div className="relative group">
        {/* Left arrow */}
        <button
          onClick={() => scroll('left')}
          className="absolute left-0 top-0 bottom-6 z-20 px-2 opacity-0 group-hover:opacity-100 transition-opacity bg-gradient-to-r from-brand-bg to-transparent"
          aria-label="Scroll left"
        >
          <div className="bg-brand-surface/90 rounded-full p-1 hover:bg-brand-card transition-colors">
            <ChevronLeft size={20} className="text-brand-text" />
          </div>
        </button>

        {/* Cards */}
        <div
          ref={scrollRef}
          className="flex gap-3 overflow-x-auto scrollbar-hide px-4 sm:px-8 pb-2"
        >
          {section.items.map((rec: RecommendedMovie) => (
            <MovieCard
              key={rec.movie.id}
              movie={rec.movie}
              explanation={rec.explanation}
              showExplanation
            />
          ))}
        </div>

        {/* Right arrow */}
        <button
          onClick={() => scroll('right')}
          className="absolute right-0 top-0 bottom-6 z-20 px-2 opacity-0 group-hover:opacity-100 transition-opacity bg-gradient-to-l from-brand-bg to-transparent"
          aria-label="Scroll right"
        >
          <div className="bg-brand-surface/90 rounded-full p-1 hover:bg-brand-card transition-colors">
            <ChevronRight size={20} className="text-brand-text" />
          </div>
        </button>
      </div>
    </section>
  );
}
