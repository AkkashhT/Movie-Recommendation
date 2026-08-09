import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Film, Eye, EyeOff, AlertCircle } from 'lucide-react';
import { authApi } from '../api';
import { useAuthStore } from '../store/auth';

// â”€â”€ Login â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { setAuth } = useAuthStore();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await authApi.login(email, password);
      setAuth({ id: data.user_id, email, username: '', role: data.role,
                 onboarding_done: data.onboarding_done, interaction_count: 0 },
               data.access_token, data.refresh_token);
      // Fetch full user profile
      const me = await authApi.me();
      setAuth(me, data.access_token, data.refresh_token);
      navigate(data.onboarding_done ? '/' : '/onboarding');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Invalid email or password.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout title="Welcome back" subtitle="Sign in to your Cinemate account">
      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label="Email" type="email" value={email} onChange={setEmail} placeholder="you@example.com" />
        <div className="space-y-1">
          <label className="text-xs font-medium text-brand-muted uppercase tracking-wider">Password</label>
          <div className="relative">
            <input
              type={showPw ? 'text' : 'password'}
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢"
              className={inputClass}
              required
            />
            <button type="button" onClick={() => setShowPw(!showPw)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-brand-muted hover:text-brand-text">
              {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 text-red-400 text-sm bg-red-400/10 rounded-lg px-3 py-2">
            <AlertCircle size={14} />
            {error}
          </div>
        )}

        <button type="submit" disabled={loading} className={submitClass}>
          {loading ? 'Signing inâ€¦' : 'Sign in'}
        </button>
      </form>

      <p className="text-center text-sm text-brand-muted mt-6">
        New to Cinemate?{' '}
        <Link to="/register" className="text-brand-amber hover:text-brand-amber-dim font-medium">
          Create an account
        </Link>
      </p>
    </AuthLayout>
  );
}

// â”€â”€ Register â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export function RegisterPage() {
  const [form, setForm] = useState({ email: '', username: '', password: '', full_name: '' });
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { setAuth } = useAuthStore();
  const navigate = useNavigate();

  const set = (k: string) => (v: string) => setForm(f => ({ ...f, [k]: v }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (form.password.length < 8) { setError('Password must be at least 8 characters.'); return; }
    setError('');
    setLoading(true);
    try {
      const data = await authApi.register(form);
      const me = await authApi.me();
      setAuth(me, data.access_token, data.refresh_token);
      navigate('/onboarding');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Registration failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout title="Join Cinemate" subtitle="Create your free account and start discovering">
      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label="Full name (optional)" type="text" value={form.full_name} onChange={set('full_name')} placeholder="Jane Smith" />
        <Field label="Email" type="email" value={form.email} onChange={set('email')} placeholder="you@example.com" required />
        <Field label="Username" type="text" value={form.username} onChange={set('username')} placeholder="cinephile42" required />
        <div className="space-y-1">
          <label className="text-xs font-medium text-brand-muted uppercase tracking-wider">Password</label>
          <div className="relative">
            <input type={showPw ? 'text' : 'password'} value={form.password}
              onChange={e => set('password')(e.target.value)} placeholder="Min. 8 characters"
              className={inputClass} required minLength={8} />
            <button type="button" onClick={() => setShowPw(!showPw)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-brand-muted hover:text-brand-text">
              {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 text-red-400 text-sm bg-red-400/10 rounded-lg px-3 py-2">
            <AlertCircle size={14} />
            {error}
          </div>
        )}

        <button type="submit" disabled={loading} className={submitClass}>
          {loading ? 'Creating accountâ€¦' : 'Create account'}
        </button>
      </form>

      <p className="text-center text-sm text-brand-muted mt-6">
        Already have an account?{' '}
        <Link to="/login" className="text-brand-amber hover:text-brand-amber-dim font-medium">Sign in</Link>
      </p>
    </AuthLayout>
  );
}

// â”€â”€ Shared â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const inputClass = "w-full bg-brand-surface border border-brand-border rounded-xl px-4 py-2.5 text-sm text-brand-text placeholder:text-brand-muted focus:outline-none focus:border-brand-amber transition-colors";
const submitClass = "w-full bg-brand-amber text-black font-semibold py-2.5 rounded-xl hover:bg-brand-amber-dim transition-colors disabled:opacity-60 disabled:cursor-not-allowed";

function Field({ label, type, value, onChange, placeholder, required }: {
  label: string; type: string; value: string;
  onChange: (v: string) => void; placeholder: string; required?: boolean;
}) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-brand-muted uppercase tracking-wider">{label}</label>
      <input type={type} value={value} onChange={e => onChange(e.target.value)}
        placeholder={placeholder} className={inputClass} required={required} />
    </div>
  );
}

function AuthLayout({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <div className="min-h-screen pt-14 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <Link to="/" className="inline-flex items-center gap-2 mb-6">
            <Film size={28} className="text-brand-amber" />
            <span className="font-display text-2xl font-bold text-brand-text">
              Cine<span className="text-brand-amber">mate</span>
            </span>
          </Link>
          <h1 className="font-display text-2xl font-semibold text-brand-text">{title}</h1>
          <p className="text-brand-muted text-sm mt-1">{subtitle}</p>
        </div>
        <div className="bg-brand-surface border border-brand-border rounded-2xl p-6">
          {children}
        </div>
      </div>
    </div>
  );
}


