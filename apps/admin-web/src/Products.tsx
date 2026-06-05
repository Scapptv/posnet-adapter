import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  ApiError,
  api,
  MOVEMENT_KINDS,
  type InventoryLevel,
  type MovementKind,
  type Product,
  type ProductDetail,
  type Variant,
  type Warehouse,
} from './api';

function money(minor: number, currency: string): string {
  return `${(minor / 100).toFixed(2)} ${currency}`;
}

export function Products() {
  const [products, setProducts] = useState<Product[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [currency, setCurrency] = useState('AZN');
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    try {
      setProducts(await api.listProducts());
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
      const p = await api.createProduct({ name, currency });
      setName('');
      await reload();
      setSelected(p.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'yaratma xətası');
    }
  }

  return (
    <section>
      <h2>Məhsullar</h2>
      {error && <p className="error">{error}</p>}
      <div className="split">
        <div>
          <table>
            <thead>
              <tr>
                <th>Ad</th>
                <th>Valyuta</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {products.map((p) => (
                <tr
                  key={p.id}
                  className={p.id === selected ? 'selected' : 'clickable'}
                  onClick={() => setSelected(p.id)}
                >
                  <td>{p.name}</td>
                  <td>{p.currency}</td>
                  <td>{p.status}</td>
                </tr>
              ))}
              {products.length === 0 && (
                <tr>
                  <td colSpan={3} className="muted">
                    hələ məhsul yoxdur
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <form onSubmit={create} className="row">
            <input placeholder="Məhsul adı" value={name} onChange={(e) => setName(e.target.value)} />
            <input
              className="cur"
              value={currency}
              onChange={(e) => setCurrency(e.target.value.toUpperCase())}
              maxLength={3}
            />
            <button type="submit" disabled={!name}>
              Məhsul yarat
            </button>
          </form>
        </div>
        <div>{selected && <Detail productId={selected} />}</div>
      </div>
    </section>
  );
}

function Detail({ productId }: { productId: string }) {
  const [detail, setDetail] = useState<ProductDetail | null>(null);
  const [sku, setSku] = useState('');
  const [price, setPrice] = useState('');
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setDetail(await api.getProduct(productId));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'yüklənmə xətası');
    }
  }, [productId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function addVariant(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const major = Number.parseFloat(price);
    if (Number.isNaN(major)) {
      setError('qiymət düzgün deyil');
      return;
    }
    try {
      await api.addVariant(productId, { sku, base_price_minor: Math.round(major * 100) });
      setSku('');
      setPrice('');
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'variant xətası');
    }
  }

  if (!detail) return <p className="muted">yüklənir…</p>;

  return (
    <div className="card">
      <h3>{detail.name}</h3>
      {error && <p className="error">{error}</p>}
      {detail.variants.map((v) => (
        <VariantRow key={v.id} variant={v} currency={detail.currency} />
      ))}
      {detail.variants.length === 0 && <p className="muted">variant yoxdur</p>}
      <form onSubmit={addVariant} className="row">
        <input placeholder="SKU" value={sku} onChange={(e) => setSku(e.target.value)} />
        <input
          placeholder="Qiymət (5.00)"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
        />
        <button type="submit" disabled={!sku || !price}>
          Variant + qiymət
        </button>
      </form>
    </div>
  );
}

function VariantRow({ variant, currency }: { variant: Variant; currency: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="variant">
      <div className="variant-head clickable" onClick={() => setOpen((o) => !o)}>
        <strong>{variant.sku}</strong>
        <span>{money(variant.base_price_minor, currency)}</span>
        <span className="muted small">{open ? '▾ stok' : '▸ stok'}</span>
      </div>
      {open && <InventoryPanel variantId={variant.id} />}
    </div>
  );
}

function InventoryPanel({ variantId }: { variantId: string }) {
  const [levels, setLevels] = useState<InventoryLevel[]>([]);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [warehouseId, setWarehouseId] = useState('');
  const [kind, setKind] = useState<MovementKind>('in');
  const [qty, setQty] = useState('');
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [lv, wh] = await Promise.all([api.getInventory(variantId), api.listWarehouses()]);
      setLevels(lv);
      setWarehouses(wh);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'stok yüklənmə xətası');
    }
  }, [variantId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // Default-select the first warehouse once they load.
  useEffect(() => {
    if (!warehouseId && warehouses.length > 0) setWarehouseId(warehouses[0].id);
  }, [warehouses, warehouseId]);

  const warehouseName = (id: string) => warehouses.find((w) => w.id === id)?.name ?? id.slice(0, 8);

  async function move(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const n = Number.parseInt(qty, 10);
    if (Number.isNaN(n) || n <= 0) {
      setError('miqdar müsbət tam olmalıdır');
      return;
    }
    try {
      await api.applyMovement({ variant_id: variantId, warehouse_id: warehouseId, kind, qty: n });
      setQty('');
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'hərəkət xətası');
    }
  }

  return (
    <div className="inventory">
      {error && <p className="error small">{error}</p>}
      <table className="small">
        <thead>
          <tr>
            <th>Anbar</th>
            <th>Qty</th>
            <th>Rezerv</th>
            <th>Mövcud</th>
          </tr>
        </thead>
        <tbody>
          {levels.map((l) => (
            <tr key={l.warehouse_id}>
              <td>{warehouseName(l.warehouse_id)}</td>
              <td>{l.qty}</td>
              <td>{l.reserved_qty}</td>
              <td>
                <strong>{l.available}</strong>
              </td>
            </tr>
          ))}
          {levels.length === 0 && (
            <tr>
              <td colSpan={4} className="muted">
                stok yoxdur
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <form onSubmit={move} className="row small">
        <select value={kind} onChange={(e) => setKind(e.target.value as MovementKind)}>
          {MOVEMENT_KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <select value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}>
          {warehouses.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
        <input className="cur" placeholder="miqdar" value={qty} onChange={(e) => setQty(e.target.value)} />
        <button type="submit" disabled={!warehouseId || !qty}>
          Tətbiq
        </button>
      </form>
    </div>
  );
}
