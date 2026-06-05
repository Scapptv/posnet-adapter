import { useEffect, useState, type FormEvent } from 'react';
import { ApiError, api, type Warehouse } from './api';

export function Warehouses() {
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [name, setName] = useState('');
  const [type, setType] = useState('store');
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    try {
      setWarehouses(await api.listWarehouses());
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'yüklənmə xətası');
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  async function create(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.createWarehouse({ name, type });
      setName('');
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'yaratma xətası');
    }
  }

  return (
    <section>
      <h2>Anbarlar</h2>
      <p className="muted">Onlayn-satışlı anbar(lar) stokun marketplace-ə çıxan mənbəyidir.</p>
      {error && <p className="error">{error}</p>}
      <table>
        <thead>
          <tr>
            <th>Ad</th>
            <th>Tip</th>
          </tr>
        </thead>
        <tbody>
          {warehouses.map((w) => (
            <tr key={w.id}>
              <td>{w.name}</td>
              <td>{w.type}</td>
            </tr>
          ))}
          {warehouses.length === 0 && (
            <tr>
              <td colSpan={2} className="muted">
                hələ anbar yoxdur
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <form onSubmit={create} className="row">
        <input placeholder="Anbar adı" value={name} onChange={(e) => setName(e.target.value)} />
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="store">store</option>
          <option value="warehouse">warehouse</option>
        </select>
        <button type="submit" disabled={!name}>
          Anbar əlavə et
        </button>
      </form>
    </section>
  );
}
