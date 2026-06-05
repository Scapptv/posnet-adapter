import { useState } from 'react';
import { clearToken, getToken } from './api';
import { Channels } from './Channels';
import { Login } from './Login';
import { Products } from './Products';
import { Warehouses } from './Warehouses';

type Tab = 'products' | 'warehouses' | 'channels';

const TABS: { id: Tab; label: string }[] = [
  { id: 'products', label: 'Məhsullar' },
  { id: 'warehouses', label: 'Anbarlar' },
  { id: 'channels', label: 'Kanallar' },
];

export function App() {
  const [authed, setAuthed] = useState(() => getToken() !== null);
  const [tab, setTab] = useState<Tab>('products');

  if (!authed) return <Login onLoggedIn={() => setAuthed(true)} />;

  function logout() {
    clearToken();
    setAuthed(false);
  }

  return (
    <div className="app">
      <header>
        <strong>Posnet Admin</strong>
        <nav>
          {TABS.map((t) => (
            <button
              key={t.id}
              className={tab === t.id ? 'tab on' : 'tab'}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </nav>
        <button className="logout" onClick={logout}>
          Çıxış
        </button>
      </header>
      <main>
        {tab === 'products' && <Products />}
        {tab === 'warehouses' && <Warehouses />}
        {tab === 'channels' && <Channels />}
      </main>
    </div>
  );
}
