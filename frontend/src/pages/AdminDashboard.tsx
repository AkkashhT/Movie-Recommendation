import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Shield, Users, Film, Activity, Brain, Play, RefreshCw, BarChart2, CheckCircle, AlertTriangle, Clock } from 'lucide-react';
import { adminApi } from '../api';

export function AdminDashboard() {
  const [evalRunning, setEvalRunning] = useState(false);
  const [evalResult, setEvalResult] = useState<any>(null);
  const [trainMsg, setTrainMsg] = useState('');

  const { data: dash, isLoading, refetch } = useQuery({
    queryKey: ['admin-dashboard'],
    queryFn: adminApi.getDashboard,
    refetchInterval: 30_000,
  });

  const { data: trainStatus } = useQuery({
    queryKey: ['train-status'],
    queryFn: adminApi.getTrainingStatus,
    refetchInterval: 5_000,
  });

  const { mutate: triggerTrain, isPending: training } = useMutation({
    mutationFn: adminApi.triggerTraining,
    onSuccess: (data) => setTrainMsg(data.message || 'Training started.'),
    onError: () => setTrainMsg('Failed to start training.'),
  });

  const handleEval = async () => {
    setEvalRunning(true);
    try {
      const result = await adminApi.runEvaluation();
      setEvalResult(result);
    } catch {
      setEvalResult({ error: 'Evaluation failed.' });
    } finally {
      setEvalRunning(false);
    }
  };

  const mlStatus = dash?.ml_service?.status;

  return (
    <div className="pt-20 pb-16 px-4 sm:px-8 max-w-6xl mx-auto">
      <div className="flex items-center gap-3 mb-8">
        <Shield size={22} className="text-brand-amber" />
        <h1 className="font-display text-2xl font-bold text-brand-text">Admin Dashboard</h1>
        <button onClick={() => refetch()}
          className="ml-auto p-2 text-brand-muted hover:text-brand-amber transition-colors">
          <RefreshCw size={16} />
        </button>
      </div>

      {isLoading && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          {[1,2,3,4].map(i => <div key={i} className="h-24 bg-brand-surface rounded-2xl animate-pulse" />)}
        </div>
      )}

      {dash && (
        <>
          {/* Stat cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <StatCard icon={<Users size={18} />} label="Total Users" value={dash.users?.total ?? 0} />
            <StatCard icon={<Film size={18} />} label="Movies" value={dash.movies?.total ?? 0}
              sub={`${dash.movies?.with_embeddings ?? 0} with embeddings`} />
            <StatCard icon={<Activity size={18} />} label="Interactions" value={dash.interactions?.total ?? 0}
              sub={`${dash.interactions?.ratings ?? 0} ratings`} />
            <StatCard
              icon={mlStatus === 'healthy' ? <CheckCircle size={18} className="text-green-400" /> : <AlertTriangle size={18} className="text-red-400" />}
              label="ML Service"
              value={mlStatus === 'healthy' ? 'Online' : 'Offline'}
              valueClass={mlStatus === 'healthy' ? 'text-green-400' : 'text-red-400'}
            />
          </div>

          {/* Interaction breakdown */}
          {dash.interactions?.by_type && (
            <div className="bg-brand-surface border border-brand-border rounded-2xl p-5 mb-6">
              <h2 className="text-sm font-medium text-brand-muted uppercase tracking-wider mb-4">Interactions by Type</h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                {Object.entries(dash.interactions.by_type).map(([type, count]: any) => (
                  <div key={type} className="bg-brand-card rounded-xl p-3">
                    <p className="text-xs text-brand-muted mb-1">{type}</p>
                    <p className="text-lg font-semibold text-brand-text">{count.toLocaleString()}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ML Models */}
          {dash.ml_service?.models?.length > 0 && (
            <div className="bg-brand-surface border border-brand-border rounded-2xl p-5 mb-6">
              <h2 className="text-sm font-medium text-brand-muted uppercase tracking-wider mb-4">ML Models</h2>
              <div className="space-y-3">
                {dash.ml_service.models.map((m: any) => (
                  <div key={m.name} className="flex items-center justify-between py-2 border-b border-brand-border last:border-0">
                    <div>
                      <p className="text-sm font-medium text-brand-text">{m.name.replace(/_/g, ' ')}</p>
                      <p className="text-xs text-brand-muted">{m.type} — {m.description}</p>
                    </div>
                    <span className={`text-xs px-2 py-1 rounded-full ${m.trained ? 'bg-green-500/20 text-green-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
                      {m.trained ? 'Ready' : 'Not trained'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Training controls */}
      <div className="grid sm:grid-cols-2 gap-4 mb-6">
        <div className="bg-brand-surface border border-brand-border rounded-2xl p-5">
          <div className="flex items-center gap-2 mb-3">
            <Brain size={16} className="text-brand-amber" />
            <h2 className="text-sm font-semibold text-brand-text">Ingest + Retrain</h2>
          </div>
          <p className="text-xs text-brand-muted mb-4">
            Re-ingests movies from TMDB and retrains all ML models (SVD, NCF, embeddings).
            Runs in background — takes 10–30 minutes.
          </p>

          {/* Training status bar */}
          {trainStatus && trainStatus.status !== 'idle' && (
            <div className="mb-4">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-brand-muted capitalize">{trainStatus.status}</span>
                <span className="text-xs text-brand-muted">{trainStatus.progress}%</span>
              </div>
              <div className="h-1.5 bg-brand-card rounded-full overflow-hidden">
                <div className="h-full bg-brand-amber rounded-full transition-all duration-500"
                  style={{ width: `${trainStatus.progress}%` }} />
              </div>
              <p className="text-xs text-brand-muted mt-1">{trainStatus.message}</p>
            </div>
          )}

          <button onClick={() => triggerTrain()} disabled={training || trainStatus?.status === 'running'}
            className="flex items-center gap-2 px-4 py-2 bg-brand-amber text-black text-sm font-medium rounded-xl hover:bg-brand-amber-dim transition-colors disabled:opacity-50">
            <Play size={14} />
            {trainStatus?.status === 'running' ? 'Training…' : 'Start Training'}
          </button>
          {trainMsg && <p className="text-xs text-brand-muted mt-2">{trainMsg}</p>}
        </div>

        <div className="bg-brand-surface border border-brand-border rounded-2xl p-5">
          <div className="flex items-center gap-2 mb-3">
            <BarChart2 size={16} className="text-brand-amber" />
            <h2 className="text-sm font-semibold text-brand-text">Run Evaluation</h2>
          </div>
          <p className="text-xs text-brand-muted mb-4">
            Computes Precision@K, Recall@K, NDCG@K, MAP, RMSE on leave-one-out splits. Takes ~1–2 min.
          </p>
          <button onClick={handleEval} disabled={evalRunning}
            className="flex items-center gap-2 px-4 py-2 bg-brand-surface border border-brand-border text-brand-text text-sm font-medium rounded-xl hover:border-brand-amber transition-colors disabled:opacity-50">
            {evalRunning ? <><Clock size={14} className="animate-spin" /> Running…</> : <><Play size={14} /> Run Evaluation</>}
          </button>

          {evalResult && !evalResult.error && (
            <div className="mt-4 grid grid-cols-2 gap-2">
              {[
                ['P@10', evalResult.precision_at_10],
                ['R@10', evalResult.recall_at_10],
                ['NDCG@10', evalResult.ndcg_at_10],
                ['MAP@10', evalResult.map_at_10],
                ['RMSE', evalResult.rmse],
                ['Coverage', evalResult.catalog_coverage],
                ['Diversity', evalResult.intra_list_diversity],
              ].map(([label, val]) => val != null && (
                <div key={label as string} className="bg-brand-card rounded-lg p-2 text-center">
                  <p className="text-xs text-brand-muted">{label}</p>
                  <p className="text-sm font-semibold text-brand-amber">
                    {typeof val === 'number' ? val.toFixed(4) : val}
                  </p>
                </div>
              ))}
            </div>
          )}
          {evalResult?.error && (
            <p className="text-xs text-red-400 mt-2">{evalResult.error}</p>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, sub, valueClass }: any) {
  return (
    <div className="bg-brand-surface border border-brand-border rounded-2xl p-5">
      <div className="flex items-center gap-2 text-brand-muted mb-2">{icon}<span className="text-xs uppercase tracking-wider">{label}</span></div>
      <p className={`text-2xl font-bold ${valueClass || 'text-brand-text'}`}>
        {typeof value === 'number' ? value.toLocaleString() : value}
      </p>
      {sub && <p className="text-xs text-brand-muted mt-1">{sub}</p>}
    </div>
  );
}
