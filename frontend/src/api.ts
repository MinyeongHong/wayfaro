const API = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}/api/v1${path}`, options);
  if (!response.ok) {
    throw new Error(response.status === 404 ? '공고를 찾을 수 없습니다.' : `요청을 처리하지 못했습니다. (HTTP ${response.status})`);
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
