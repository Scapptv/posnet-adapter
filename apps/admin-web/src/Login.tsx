import { useState, type FormEvent } from 'react';
import { ApiError, config, login } from './api';

export function Login({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [username, setUsername] = useState('owner');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username, password);
      onLoggedIn();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'naməlum xəta');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <form onSubmit={submit} className="card">
        <h1>Posnet Admin</h1>
        <p className="muted">Merchant paneli — məhsul/stok idarəsi → marketplace sync</p>
        <label>
          İstifadəçi
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
        </label>
        <label>
          Parol
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={busy || !password}>
          {busy ? 'Giriş…' : 'Giriş'}
        </button>
        <p className="muted small">
          Realm <code>{config.realm}</code> @ <code>{config.keycloakUrl}</code>
        </p>
      </form>
    </div>
  );
}
