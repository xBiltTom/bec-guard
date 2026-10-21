export const tokenKey = 'bec-guard.access-token';
export class ApiError extends Error {
  constructor(
    public status: number,
    public data: unknown,
  ) {
    super(
      status === 403
        ? 'No tienes permisos para realizar esta acción.'
        : status === 404
          ? 'No se encontró el recurso solicitado.'
          : status === 409
            ? 'El recurso cambió. Revisa su estado actual.'
            : status === 400
              ? 'Revisa los campos y vuelve a intentarlo.'
              : status === 401
                ? 'La sesión terminó. Inicia sesión de nuevo.'
                : 'El servicio no está disponible. Vuelve a intentarlo.',
    );
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
  token = sessionStorage.getItem(tokenKey),
): Promise<T> {
  const headers = new Headers(options.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body) headers.set('Content-Type', 'application/json');
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      headers,
      cache: 'no-store',
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError')
      throw error;
    throw new ApiError(0, null);
  }
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && token) {
      sessionStorage.removeItem(tokenKey);
      window.dispatchEvent(new Event('bec-session-expired'));
    }
    throw new ApiError(response.status, data);
  }
  return data as T;
}
export function message(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : 'No se pudo completar la operación. Vuelve a intentarlo.';
}

export async function authenticatedDownload(
  path: string,
  signal?: AbortSignal,
): Promise<void> {
  const token = sessionStorage.getItem(tokenKey);
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      cache: 'no-store',
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError')
      throw error;
    throw new ApiError(0, null);
  }
  if (!response.ok) {
    if (response.status === 401 && token) {
      sessionStorage.removeItem(tokenKey);
      window.dispatchEvent(new Event('bec-session-expired'));
    }
    throw new ApiError(response.status, null);
  }
  const extension = path.split('?')[0].endsWith('.xlsx') ? 'xlsx' : 'pdf';
  const suggested = /filename="?([^";]+)"?/i
    .exec(response.headers.get('Content-Disposition') || '')?.[1]
    ?.trim();
  const filename =
    suggested &&
    /^bec-guard-operational-\d{8}\.(pdf|xlsx)$/.test(suggested) &&
    suggested.endsWith(`.${extension}`)
      ? suggested
      : `bec-guard-operational.${extension}`;
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  try {
    link.href = url;
    link.download = filename;
    document.body.append(link);
    link.click();
  } finally {
    link.remove();
    URL.revokeObjectURL(url);
  }
}
