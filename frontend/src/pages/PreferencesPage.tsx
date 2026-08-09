import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Check, Search, X, Settings, AlertCircle } from 'lucide-react';
import { usersApi } from '../api';
import { useAuthStore } from '../store/auth';

export function PreferencesPage() {
  const { user } = useAuthStore();
  const qc = useQueryClient();

  const { data: genres = [] } = useQuery({
    queryKey: ['genres'],
    queryFn: usersApi.getGenres,
  });

  const { data: prefs } = useQuery({
    queryKey: ['preferences'],
    queryFn: usersApi.getPreferences,
  });

  const [selectedGenres, setSelectedGenres] = useState<number[]>([]);
  const [selectedActors, setSelectedActors] = useState<any[]>([]);
  const [selectedDirectors, setSelectedDirectors] = useState<any[]>([]);
  const [actorSearch, setActorSearch] = useState('');
  const [directorSearch, setDirectorSearch] = useState('');
  const [actorResults, setActorResults] = useState<any[]>([]);
  const [directorResults, setDirectorResults] = useState<any[]>([]);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (prefs) {
      setSelectedGenres(prefs.genre_ids || []);
      // We can't reconstruct Person objects from just IDs without another fetch
      // For simplicity show IDs; in production fetch person details
    }
  }, [prefs]);

  useEffect(() => {
    if (actorSearch.length < 2) { setActorResults([]); return; }
    const t = setTimeout(() =>
      usersApi.searchPersons(actorSearch).then(r =>
        setActorResults(r.filter((p: any) => p.known_for_dept === 'Acting' || !p.known_for_dept))
      ), 250);
    return () => clearTimeout(t);
  }, [actorSearch]);

  useEffect(() => {
    if (directorSearch.length < 2) { setDirectorResults([]); return; }
    const t = setTimeout(() =>
      usersApi.searchPersons(directorSearch).then(r =>
        setDirectorResults(r.filter((p: any) => p.known_for_dept === 'Directing' || !p.known_for_dept))
      ), 250);
    return () => clearTimeout(t);
  }, [directorSearch]);

  const { mutate: save, isPending } = useMutation({
    mutationFn: () => usersApi.updatePreferences({
      genre_ids: selectedGenres,
      actor_ids: selectedActors.map((a: any) => a.id),
      director_ids: selectedDirectors.map((d: any) => d.id),
    }),
    onSuccess: () => {
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
      qc.invalidateQueries({ queryKey: ['home'] });
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to save preferences.');
    },
  });

  const toggleGenre = (id: number) =>
    setSelectedGenres(g => g.includes(id) ? g.filter(x => x !== id) : [...g, id]);

  const togglePerson = (p: any, list: any[], setter: (v: any[]) => void) => {
    setter(list.find((x: any) => x.id === p.id) ? list.filter((x: any) => x.id !== p.id) : [...list, p]);
  };

  return (
    <div className="pt-20 pb-16 px-4 sm:px-8 max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-8">
        <Settings size={22} className="text-brand-amber" />
        <h1 className="font-display text-2xl font-bold text-brand-text">My Preferences</h1>
      </div>

      {/* Profile info */}
      <div className="bg-brand-surface border border-brand-border rounded-2xl p-5 mb-6">
        <h2 className="text-sm font-medium text-brand-muted uppercase tracking-wider mb-3">Account</h2>
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-full bg-brand-amber flex items-center justify-center">
            <span className="text-lg font-bold text-black">{user?.username?.[0]?.toUpperCase()}</span>
          </div>
          <div>
            <p className="font-medium text-brand-text">{user?.username}</p>
            <p className="text-sm text-brand-muted">{user?.email}</p>
          </div>
        </div>
      </div>

      {/* Genre prefs */}
      <div className="bg-brand-surface border border-brand-border rounded-2xl p-5 mb-4">
        <h2 className="text-sm font-medium text-brand-muted uppercase tracking-wider mb-4">Favourite Genres</h2>
        <div className="flex flex-wrap gap-2">
          {genres.map((g: any) => (
            <button key={g.id} onClick={() => toggleGenre(g.id)}
              className={`px-3 py-1.5 rounded-full text-sm transition-all border ${
                selectedGenres.includes(g.id)
                  ? 'bg-brand-amber text-black border-brand-amber'
                  : 'border-brand-border text-brand-muted hover:border-brand-amber'
              }`}>
              {selectedGenres.includes(g.id) && <Check size={11} className="inline mr-1" />}
              {g.name}
            </button>
          ))}
        </div>
      </div>

      {/* Actor prefs */}
      <PersonPrefSection
        title="Favourite Actors"
        search={actorSearch}
        onSearch={setActorSearch}
        results={actorResults}
        selected={selectedActors}
        onToggle={(p: any) => togglePerson(p, selectedActors, setSelectedActors)}
      />

      {/* Director prefs */}
      <PersonPrefSection
        title="Favourite Directors"
        search={directorSearch}
        onSearch={setDirectorSearch}
        results={directorResults}
        selected={selectedDirectors}
        onToggle={(p: any) => togglePerson(p, selectedDirectors, setSelectedDirectors)}
      />

      {/* Save */}
      {error && (
        <div className="flex items-center gap-2 text-red-400 text-sm bg-red-400/10 rounded-xl px-4 py-3 mb-4">
          <AlertCircle size={14} /> {error}
        </div>
      )}

      <button onClick={() => save()} disabled={isPending}
        className="w-full bg-brand-amber text-black font-semibold py-3 rounded-xl hover:bg-brand-amber-dim transition-colors disabled:opacity-60">
        {isPending ? 'Saving…' : saved ? '✓ Saved!' : 'Save preferences'}
      </button>
    </div>
  );
}

function PersonPrefSection({ title, search, onSearch, results, selected, onToggle }: any) {
  return (
    <div className="bg-brand-surface border border-brand-border rounded-2xl p-5 mb-4">
      <h2 className="text-sm font-medium text-brand-muted uppercase tracking-wider mb-4">{title}</h2>
      <div className="relative mb-3">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-muted" />
        <input value={search} onChange={e => onSearch(e.target.value)} placeholder="Search…"
          className="w-full bg-brand-card border border-brand-border rounded-xl pl-9 pr-4 py-2 text-sm text-brand-text placeholder:text-brand-muted focus:outline-none focus:border-brand-amber transition-colors" />
      </div>
      {results.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-3 max-h-40 overflow-y-auto">
          {results.map((p: any) => (
            <button key={p.id} onClick={() => onToggle(p)}
              className={`text-sm px-3 py-1.5 rounded-lg border transition-all text-left ${
                selected.find((s: any) => s.id === p.id)
                  ? 'bg-brand-amber/20 border-brand-amber text-brand-amber'
                  : 'border-brand-border text-brand-text hover:border-brand-amber/50'
              }`}>
              {p.name}
            </button>
          ))}
        </div>
      )}
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {selected.map((p: any) => (
            <span key={p.id} className="flex items-center gap-1.5 bg-brand-amber/20 text-brand-amber text-xs px-3 py-1 rounded-full">
              {p.name}
              <button onClick={() => onToggle(p)}><X size={10} /></button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
