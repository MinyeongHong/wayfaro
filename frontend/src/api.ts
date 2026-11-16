import { API } from './config';

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try { response = await fetch(`${API}/api/v1${path}`, options); } catch { throw new Error('The connection could not be completed. Please try again.'); }
  if (!response.ok) {
    throw new Error(response.status === 404 ? 'The job could not be found.' : `The request could not be completed. (HTTP ${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function safeUrl(value: string | null): string | null {
  if (!value || /[\s\\\u0000-\u001f]/.test(value)) return null;
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}
