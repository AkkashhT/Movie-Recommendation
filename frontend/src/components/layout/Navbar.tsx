import { useState, useRef, useEffect } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { Search, LogOut, Settings, Shield, Bookmark, Film, X } from "lucide-react";
import { useAuthStore } from "../../store/auth";
import { searchApi } from "../../api";

interface AutocompleteResult {
  id: number;
  title: string;
  year?: number;
}

export function Navbar() {
  const { user, logout, isAuthenticated, isAdmin } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [suggestions, setSuggestions] = useState<AutocompleteResult[]>([]);
  const [showDropdown, setShowDropdown] = useState<boolean>(false);
  const [userMenuOpen, setUserMenuOpen] = useState<boolean>(false);
  const searchRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleSearchInput = (q: string) => {
    setSearchQuery(q);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (q.length < 2) { setSuggestions([]); setShowDropdown(false); return; }
    debounceRef.current = setTimeout(async () => {
      try {
        const results = await searchApi.autocomplete(q);
        setSuggestions(results);
        setShowDropdown(true);
      } catch { setSuggestions([]); }
    }, 200);
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setShowDropdown(false);
    navigate(`/search?q=${encodeURIComponent(searchQuery.trim())}`);
  };

  const handleLogout = () => {
    setUserMenuOpen(false);
    logout();
    navigate("/login");
  };

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-brand-bg/95 backdrop-blur-sm border-b border-brand-border">
      <div className="max-w-screen-2xl mx-auto px-4 sm:px-8 h-14 flex items-center gap-4">
        <Link to="/" className="flex items-center gap-2 flex-shrink-0">
          <Film size={22} className="text-brand-amber" />
          <span className="font-display text-lg font-bold text-brand-text hidden sm:block">
            Cine<span className="text-brand-amber">mate</span>
          </span>
        </Link>

        {isAuthenticated() && (
          <div className="hidden md:flex items-center gap-1 ml-2">
            <NavLink to="/" label="Home" active={location.pathname === "/"} />
            <NavLink to="/watchlist" label="Watchlist" active={location.pathname === "/watchlist"} />
          </div>
        )}

        <div className="flex-1 max-w-xl mx-auto" ref={searchRef}>
          <form onSubmit={handleSearchSubmit} className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-muted" />
            <input
              value={searchQuery}
              onChange={e => handleSearchInput(e.target.value)}
              placeholder="Search movies, actors, directors..."
              className="w-full bg-brand-surface border border-brand-border rounded-full pl-9 pr-9 py-1.5 text-sm text-brand-text placeholder:text-brand-muted focus:outline-none focus:border-brand-amber transition-colors"
            />
            {searchQuery && (
              <button type="button" onClick={() => { setSearchQuery(""); setSuggestions([]); setShowDropdown(false); }}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-brand-muted hover:text-brand-text">
                <X size={14} />
              </button>
            )}
            {showDropdown && suggestions.length > 0 && (
              <div className="absolute top-full mt-1 left-0 right-0 bg-brand-surface border border-brand-border rounded-xl overflow-hidden shadow-2xl z-50">
                {suggestions.map((s) => (
                  <Link key={s.id} to={`/movie/${s.id}`} onClick={() => setShowDropdown(false)}
                    className="flex items-center gap-3 px-4 py-2 hover:bg-brand-card transition-colors">
                    <Film size={14} className="text-brand-muted flex-shrink-0" />
                    <span className="text-sm text-brand-text">{s.title}</span>
                    {s.year && <span className="text-xs text-brand-muted ml-auto">{s.year}</span>}
                  </Link>
                ))}
                <button type="submit" className="w-full px-4 py-2 text-sm text-brand-amber hover:bg-brand-card transition-colors text-left border-t border-brand-border"
                  onClick={() => setShowDropdown(false)}>
                  Search for "{searchQuery}" &rarr;
                </button>
              </div>
            )}
          </form>
        </div>

        {isAuthenticated() ? (
          <div className="relative">
            <button
              onClick={() => setUserMenuOpen(prev => !prev)}
              className="flex items-center gap-2 text-brand-text hover:text-brand-amber transition-colors"
            >
              <div className="w-8 h-8 rounded-full bg-brand-amber flex items-center justify-center">
                <span className="text-sm font-bold text-black">
                  {user?.username?.[0]?.toUpperCase() || "U"}
                </span>
              </div>
            </button>

            {userMenuOpen && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setUserMenuOpen(false)} />
                <div className="absolute right-0 top-full mt-2 w-48 bg-brand-surface border border-brand-border rounded-xl overflow-hidden shadow-2xl z-50">
                  <div className="px-4 py-3 border-b border-brand-border">
                    <p className="text-sm font-medium text-brand-text">{user?.username}</p>
                    <p className="text-xs text-brand-muted truncate">{user?.email}</p>
                  </div>
                  <Link to="/watchlist" onClick={() => setUserMenuOpen(false)}
                    className="flex items-center gap-3 px-4 py-2.5 text-sm text-brand-text hover:bg-brand-card transition-colors">
                    <Bookmark size={14} className="text-brand-muted" />
                    Watchlist
                  </Link>
                  <Link to="/preferences" onClick={() => setUserMenuOpen(false)}
                    className="flex items-center gap-3 px-4 py-2.5 text-sm text-brand-text hover:bg-brand-card transition-colors">
                    <Settings size={14} className="text-brand-muted" />
                    Preferences
                  </Link>
                  {isAdmin() && (
                    <Link to="/admin" onClick={() => setUserMenuOpen(false)}
                      className="flex items-center gap-3 px-4 py-2.5 text-sm text-brand-text hover:bg-brand-card transition-colors">
                      <Shield size={14} className="text-brand-muted" />
                      Admin
                    </Link>
                  )}
                  <button onClick={handleLogout}
                    className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-red-400 hover:bg-brand-card transition-colors">
                    <LogOut size={14} />
                    Sign out
                  </button>
                </div>
              </>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <Link to="/login" className="text-sm text-brand-muted hover:text-brand-text transition-colors px-3 py-1">
              Sign in
            </Link>
            <Link to="/register" className="text-sm bg-brand-amber text-black font-medium px-3 py-1.5 rounded-lg hover:bg-brand-amber-dim transition-colors">
              Get started
            </Link>
          </div>
        )}
      </div>
    </nav>
  );
}

function NavLink({ to, label, active }: { to: string; label: string; active: boolean }) {
  return (
    <Link to={to}
      className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${active ? "text-brand-amber bg-brand-amber/10" : "text-brand-muted hover:text-brand-text"}`}>
      {label}
    </Link>
  );
}


