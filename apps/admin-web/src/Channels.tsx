import { useEffect, useState } from 'react';
import { ApiError, api, type Channel, type ChannelListing } from './api';

function synced(at: string | null): string {
  return at ? new Date(at).toLocaleString() : '—';
}

export function Channels() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [listings, setListings] = useState<ChannelListing[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    setError(null);
    try {
      const [ch, ls] = await Promise.all([api.listChannels(), api.listChannelListings()]);
      setChannels(ch);
      setListings(ls);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'yüklənmə xətası');
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  return (
    <section>
      <div className="variant-head" style={{ padding: 0 }}>
        <h2 style={{ margin: 0, flex: 1 }}>Kanallar</h2>
        <button className="tab" onClick={() => void reload()}>
          Yenilə
        </button>
      </div>
      <p className="muted">
        Məhsulu <strong>“Kanala çıxar”</strong> etdikdən sonra sync engine onu push edir və listing
        burada görünür.
      </p>
      {error && <p className="error">{error}</p>}

      <h3>Qoşulan kanallar</h3>
      <table>
        <thead>
          <tr>
            <th>Kod</th>
            <th>Ad</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {channels.map((c) => (
            <tr key={c.id}>
              <td>
                <code>{c.code}</code>
              </td>
              <td>{c.name}</td>
              <td>{c.status}</td>
            </tr>
          ))}
          {channels.length === 0 && (
            <tr>
              <td colSpan={3} className="muted">
                hələ qoşulan kanal yoxdur
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h3>Sync listinglər</h3>
      <table>
        <thead>
          <tr>
            <th>Kanal</th>
            <th>SKU</th>
            <th>Kanal ID</th>
            <th>Status</th>
            <th>Son sync</th>
          </tr>
        </thead>
        <tbody>
          {listings.map((l) => (
            <tr key={`${l.channel_id}:${l.variant_id}`}>
              <td>
                <code>{l.channel_code}</code>
              </td>
              <td>{l.sku}</td>
              <td className="muted small">{l.external_listing_id ?? '—'}</td>
              <td>{l.status}</td>
              <td className="muted small">{synced(l.last_synced_at)}</td>
            </tr>
          ))}
          {listings.length === 0 && (
            <tr>
              <td colSpan={5} className="muted">
                hələ sync olunmuş listing yoxdur
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
