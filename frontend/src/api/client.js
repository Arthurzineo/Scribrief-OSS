/* Same-origin Django session client. Credentials live only in HttpOnly cookies. */
export const API_URL = (import.meta.env?.VITE_API_URL || '/api/v1').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(status, message, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

function cookie(name) {
  const item = document.cookie.split('; ').find((part) => part.startsWith(`${name}=`));
  return item ? decodeURIComponent(item.slice(name.length + 1)) : '';
}

export async function ensureCsrf() {
  if (cookie('csrftoken')) return cookie('csrftoken');
  const response = await fetch(`${API_URL}/csrf/`, { credentials: 'same-origin' });
  if (!response.ok) throw new ApiError(response.status, 'Não foi possível iniciar a sessão.');
  return cookie('csrftoken');
}

function errorMessage(body, status) {
  const error = body?.error;
  if (typeof error?.message === 'string') {
    const first = Object.entries(error.fields || {})[0];
    if (first) {
      const detail = Array.isArray(first[1]) ? first[1][0] : first[1];
      if (typeof detail === 'string') return `${error.message} ${first[0]}: ${detail.slice(0, 180)}`;
    }
    return error.message;
  }
  if (typeof body?.detail === 'string') return body.detail;
  if (status === 403) return 'Sessão ou verificação CSRF inválida. Recarregue a página.';
  if (status === 413) return 'O arquivo ultrapassa o limite permitido.';
  if (status === 429) return 'Limite temporário atingido. Aguarde e tente novamente.';
  return `Erro ${status}`;
}

async function parse(response, { silentUnauthorized = false } = {}) {
  const raw = await response.text();
  let body;
  try { body = raw ? JSON.parse(raw) : null; } catch { body = raw; }
  if (!response.ok) {
    if (response.status === 401 && !silentUnauthorized) window.dispatchEvent(new Event('ata:unauthorized'));
    throw new ApiError(response.status, errorMessage(body, response.status), body);
  }
  return body;
}

export async function request(method, path, {
  json, query, signal, headers = {}, silentUnauthorized = false,
} = {}) {
  const params = new URLSearchParams(Object.entries(query || {}).filter(([, value]) => value != null && value !== ''));
  const suffix = params.size ? `?${params}` : '';
  const mutating = !['GET', 'HEAD', 'OPTIONS'].includes(method);
  if (mutating) await ensureCsrf();
  const endpoint = path.startsWith('/api/') ? path : `${API_URL}${path}`;
  const response = await fetch(`${endpoint}${suffix}`, {
    method,
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      ...(json !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(mutating ? { 'X-CSRFToken': cookie('csrftoken') } : {}),
      ...headers,
    },
    body: json === undefined ? undefined : JSON.stringify(json),
    signal,
  });
  return parse(response, { silentUnauthorized });
}

/** Best-effort small request that can outlive page navigation; server TTL remains the fallback. */
export function postKeepalive(path) {
  const token = cookie('csrftoken');
  if (!token) return;
  fetch(`${API_URL}${path}`, {
    method: 'POST', credentials: 'same-origin', keepalive: true,
    headers: { Accept: 'application/json', 'X-CSRFToken': token },
  }).catch(() => {});
}

/** XMLHttpRequest is needed for progress and cancellation of large uploads. */
export function upload(path, formData, onProgress) {
  const xhr = new XMLHttpRequest();
  const promise = (async () => {
    await ensureCsrf();
    return new Promise((resolve, reject) => {
      xhr.open('POST', `${API_URL}${path}`);
      xhr.withCredentials = true;
      xhr.setRequestHeader('X-CSRFToken', cookie('csrftoken'));
      xhr.setRequestHeader('Accept', 'application/json');
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress?.(event.loaded / event.total);
      };
      xhr.onload = () => {
        let body;
        try { body = xhr.responseText ? JSON.parse(xhr.responseText) : null; } catch { body = null; }
        if (xhr.status >= 200 && xhr.status < 300) resolve(body);
        else {
          if (xhr.status === 401) window.dispatchEvent(new Event('ata:unauthorized'));
          reject(new ApiError(xhr.status, errorMessage(body, xhr.status), body));
        }
      };
      xhr.onerror = () => reject(new ApiError(0, 'Não foi possível conectar ao servidor.'));
      xhr.onabort = () => reject(new ApiError(-1, 'Envio cancelado.'));
      xhr.send(formData);
    });
  })();
  return { promise, abort: () => xhr.abort() };
}
