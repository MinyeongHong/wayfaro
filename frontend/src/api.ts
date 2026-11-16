export function safeUrl(value: string | null): string | null {
  if (!value || /[\s\\\u0000-\u001f]/.test(value)) return null;
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}
