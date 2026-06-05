import { useState } from 'react';
import { clearToken, getToken } from './api';
import { Login } from './Login';
import { Products } from './Products';
import { Warehouses } from './Warehouses';

type Tab = 'products' | 'warehouses';

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
          <button className={tab === 'products' ? 'tab on' : 'tab'} onClick={() => setTab('products')}>
            Məhsullar
          </button>
          <button
            className={tab === 'warehouses' ? 'tab on' : 'tab'}
            onClick={() => setTab('warehouses')}
          >
            Anbarlar
          </button>
        </nav>
        <button className="logout" onClick={logout}>
          Çıxış
        </button>
      </header>
      <main>{tab === 'products' ? <Products /> : <Warehouses />}</main>
    </div>
  );
}
