import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Check, Search, X, ChevronRight, Film } from 'lucide-react';
import { usersApi } from '../api';
import { useAuthStore } from '../store/auth';

type Step = 'genres' | 'actors' | 'directors';

export function OnboardingPage() {
  const [step, setStep] = useState<Step>('genres');
  const [selectedGenres, setSelectedGenres] = useState<number[]>([]);
  const [selectedActors, setSelectedActors] = useState<any[]>([]);
  const [selectedDirectors, setSelectedDirectors] = useState<any[]>([]);
  const [genres, setGenres] = useState<any[]>([]);
  const [personSearch, setPersonSearch] = useState('');
  const [personResults, setPersonResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const { setUser } = useAuthStore();
  const navigate = useNavigate();

  useEffect(() => {
    usersApi.getGenres().then(setGenres);
  }, []);

  useEffect(() => {
    if (personSearch.length < 2) { setPersonResults([]); return; }
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const results = await usersApi.searchPersons(personSearch);
        // Filter: for actors step show Acting; for directors show Directing
        const filtered = results.filter((p: any) =>
          step === 'actors'
            ? p.known_for_dept === 'Acting' || !p.known_for_dept
            : p.known_for_dept === 'Directing' || !p.known_for_dept
        );
        setPersonResults(filtered);
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [personSearch, step]);

  const toggleGenre = (id: number) =>
    setSelectedGenres(g => g.includes(id) ? g.filter(x => x !== id) : [...g, id]);

  const togglePerson = (person: any, selected: any[], setter: (v: any[]) => void) => {
    if (selected.find((p: any) => p.id === person.id)) {
      setter(selected.filter((p: any) => p.id !== person.id));
    } else {
      setter([...selected, person]);
    }
  };

  const handleSubmit = async () => {
    if (selectedGenres.length < 3 || selectedActors.length < 2 || selectedDirectors.length < 1) {
      setError('Please complete all selections before continuing.');
      return;
    }
    setSubmitting(true);
    try {
      await usersApi.completeOnboarding({
        genre_ids: selectedGenres,
        actor_ids: selectedActors.map((a: any) => a.id),
        director_ids: selectedDirectors.map((d: any) => d.id),
      });
      const me = await import('../api').then(m => m.authApi.me());
      setUser(me);
      navigate('/');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Something went wrong. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const steps: { key: Step; label: string; min: number; current: number }[] = [
    { key: 'genres', label: 'Genres', min: 3, current: selectedGenres.length },
    { key: 'actors', label: 'Actors', min: 2, current: selectedActors.length },
    { key: 'directors', label: 'Directors', min: 1, current: selectedDirectors.length },
  ];

  return (
    <div className="min-h-screen pt-14 pb-12 px-4">
      <div className="max-w-2xl mx-auto pt-10">
        {/* Header */}
        <div className="text-center mb-8">
          <Film size={32} className="text-brand-amber mx-auto mb-3" />
          <h1 className="font-display text-3xl font-bold text-brand-text">Set up your taste</h1>
          <p className="text-brand-muted mt-2">
            We'll use this to personalise your recommendations from day one.
          </p>
        </div>

        {/* Step progress */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {steps.map((s, i) => (
            <div key={s.key} className="flex items-center gap-2">
              <button
                onClick={() => setStep(s.key)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                  step === s.key
                    ? 'bg-brand-amber text-black'
                    : s.current >= s.min
                    ? 'bg-brand-amber/20 text-brand-amber'
                    : 'bg-brand-surface text-brand-muted'
                }`}
              >
                {s.current >= s.min && <Check size={12} />}
                {s.label}
                <span className="opacity-70">{s.current}/{s.min}+</span>
              </button>
              {i < steps.length - 1 && <ChevronRight size={14} className="text-brand-border" />}
            </div>
          ))}
        </div>

        {/* Step content */}
        <div className="bg-brand-surface border border-brand-border rounded-2xl p-6">
          {step === 'genres' && (
            <GenreStep
              genres={genres}
              selected={selectedGenres}
              onToggle={toggleGenre}
              onNext={() => setStep('actors')}
            />
          )}
          {step === 'actors' && (
            <PersonStep
              title="Favourite actors"
              subtitle="Pick at least 2 actors you love Ã¢ we'll find more movies with them."
              minCount={2}
              search={personSearch}
              onSearch={setPersonSearch}
              results={personResults}
              selected={selectedActors}
              onToggle={(p: any) => togglePerson(p, selectedActors, setSelectedActors)}
              loading={loading}
              onNext={() => setStep('directors')}
            />
          )}
          {step === 'directors' && (
            <PersonStep
              title="Favourite directors"
              subtitle="Pick at least 1 director whose style speaks to you."
              minCount={1}
              search={personSearch}
              onSearch={setPersonSearch}
              results={personResults}
              selected={selectedDirectors}
              onToggle={(p: any) => togglePerson(p, selectedDirectors, setSelectedDirectors)}
              loading={loading}
              onNext={handleSubmit}
              isLastStep
              submitting={submitting}
            />
          )}
        </div>

        {error && (
          <p className="text-red-400 text-sm text-center mt-4">{error}</p>
        )}
      </div>
    </div>
  );
}

function GenreStep({ genres, selected, onToggle, onNext }: any) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-display text-xl font-semibold text-brand-text">Favourite genres</h2>
        <p className="text-brand-muted text-sm mt-1">Pick at least 3 that excite you.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {genres.map((g: any) => (
          <button
            key={g.id}
            onClick={() => onToggle(g.id)}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-all ${
              selected.includes(g.id)
                ? 'bg-brand-amber text-black'
                : 'bg-brand-card border border-brand-border text-brand-muted hover:border-brand-amber hover:text-brand-text'
            }`}
          >
            {selected.includes(g.id) && <Check size={12} className="inline mr-1" />}
            {g.name}
          </button>
        ))}
      </div>
      <button
        onClick={onNext}
        disabled={selected.length < 3}
        className="w-full bg-brand-amber text-black font-semibold py-2.5 rounded-xl hover:bg-brand-amber-dim transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Next: Actors Ã¢ 
      </button>
    </div>
  );
}

function PersonStep({ title, subtitle, minCount, search, onSearch, results, selected, onToggle, loading, onNext, isLastStep, submitting }: any) {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-display text-xl font-semibold text-brand-text">{title}</h2>
        <p className="text-brand-muted text-sm mt-1">{subtitle}</p>
      </div>

      {/* Search */}
      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-muted" />
        <input
          value={search}
          onChange={e => onSearch(e.target.value)}
          placeholder="Search by nameÃ¢
          className="w-full bg-brand-card border border-brand-border rounded-xl pl-9 pr-4 py-2.5 text-sm text-brand-text placeholder:text-brand-muted focus:outline-none focus:border-brand-amber transition-colors"
        />
        {loading && <div className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 border-2 border-brand-amber border-t-transparent rounded-full animate-spin" />}
      </div>

      {/* Results */}
      {results.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-56 overflow-y-auto pr-1">
          {results.map((p: any) => {
            const sel = selected.find((s: any) => s.id === p.id);
            return (
              <button
                key={p.id}
                onClick={() => onToggle(p)}
                className={`flex items-center gap-2 px-3 py-2 rounded-xl text-sm transition-all border ${
                  sel
                    ? 'bg-brand-amber/20 border-brand-amber text-brand-amber'
                    : 'bg-brand-card border-brand-border text-brand-text hover:border-brand-amber/50'
                }`}
              >
                {sel && <Check size={12} />}
                <span className="truncate">{p.name}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Selected pills */}
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {selected.map((p: any) => (
            <span key={p.id} className="flex items-center gap-1.5 bg-brand-amber/20 text-brand-amber text-xs px-3 py-1 rounded-full">
              {p.name}
              <button onClick={() => onToggle(p)} className="hover:text-brand-amber-dim">
                <X size={10} />
              </button>
            </span>
          ))}
        </div>
      )}

      <button
        onClick={onNext}
        disabled={selected.length < minCount || submitting}
        className="w-full bg-brand-amber text-black font-semibold py-2.5 rounded-xl hover:bg-brand-amber-dim transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {submitting ? 'Setting upÃ¢ : isLastStep ? 'Start discovering Ã¢  : 'Next Ã¢ 
      </button>
    </div>
  );
}

