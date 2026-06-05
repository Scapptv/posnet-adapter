// API client for the Posnet hub core (AI-2.7 admin-web minimal).
//
// Auth is a Keycloak password grant against the `posnet-pos` public client —
// pragmatic for a dev/demo merchant panel (production uses the OIDC redirect +
// PKCE flow). The token is kept in localStorage; every API call carries it as a
// Bearer header, and a 401 clears it so the app falls back to the login screen.

const env = import.meta.env as Record<string, string | undefined>;

export const config = {
  apiBase: env.VITE_API_BASE ?? 'http://localhost:8000',
  keycloakUrl: env.VITE_KEYCLOAK_URL ?? 'http://localhost:8080',
  realm: env.VITE_KEYCLOAK_REALM ?? 'posnet',
  clientId: env.VITE_KEYCLOAK_CLIENT ?? 'posnet-pos',
};

const TOKEN_KEY = 'posnet_token';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`${status}: ${detail}`);
  }
}

export async function login(username: string, password: string): Promise<void> {
  const url = `${config.keycloakUrl}/realms/${config.realm}/protocol/openid-connect/token`;
  const body = new URLSearchParams({
    grant_type: 'password',
    client_id: config.clientId,
    username,
    password,
  });
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  if (!res.ok) {
    throw new ApiError(res.status, 'giriş alınmadı — istifadəçi/parol yoxla');
  }
  const data = (await res.json()) as { access_token?: string };
  if (!data.access_token) throw new ApiError(500, 'token cavabda yoxdur');
  localStorage.setItem(TOKEN_KEY, data.access_token);
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${config.apiBase}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (res.status === 401) {
    clearToken();
    throw new ApiError(401, 'sessiya bitdi — yenidən giriş');
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const problem = (await res.json()) as { detail?: string; title?: string };
      detail = problem.detail ?? problem.title ?? detail;
    } catch {
      // non-JSON error body — keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---- types (mirror the core API response models) ----

export interface Product {
  id: string;
  name: string;
  brand: string | null;
  category_path: string[];
  currency: string;
  status: string;
  store_id: string | null;
}

export interface Variant {
  id: string;
  product_id: string;
  sku: string;
  barcode: string | null;
  name: string | null;
  attributes: Record<string, string>;
  base_price_minor: number;
  cost_price_minor: number | null;
}

export interface ProductDetail extends Product {
  variants: Variant[];
  images: { url: string; sort_order: number }[];
}

export interface Warehouse {
  id: string;
  name: string;
  type: string;
}

export interface InventoryLevel {
  variant_id: string;
  warehouse_id: string;
  qty: number;
  reserved_qty: number;
  min_qty: number;
  version: number;
  available: number;
}

export const MOVEMENT_KINDS = ['in', 'out', 'reserve', 'unreserve', 'adjust'] as const;
export type MovementKind = (typeof MOVEMENT_KINDS)[number];

// ---- endpoints ----

export const api = {
  listProducts: (q?: string) =>
    apiFetch<Product[]>(`/v1/products${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  createProduct: (body: { name: string; currency: string; brand?: string }) =>
    apiFetch<Product>('/v1/products', { method: 'POST', body: JSON.stringify(body) }),
  getProduct: (id: string) => apiFetch<ProductDetail>(`/v1/products/${id}`),
  addVariant: (productId: string, body: { sku: string; base_price_minor: number; barcode?: string }) =>
    apiFetch<Variant>(`/v1/products/${productId}/variants`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  listWarehouses: () => apiFetch<Warehouse[]>('/v1/warehouses'),
  createWarehouse: (body: { name: string; type: string }) =>
    apiFetch<Warehouse>('/v1/warehouses', { method: 'POST', body: JSON.stringify(body) }),
  getInventory: (variantId: string) =>
    apiFetch<InventoryLevel[]>(`/v1/inventory?variant_id=${variantId}`),
  applyMovement: (body: {
    variant_id: string;
    warehouse_id: string;
    kind: MovementKind;
    qty: number;
    reference?: string;
  }) => apiFetch<InventoryLevel>('/v1/inventory/movements', { method: 'POST', body: JSON.stringify(body) }),
};
