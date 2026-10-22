const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8022';

export async function requestResponse(path, { token, headers = {}, ...options } = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { message = (await response.json()).detail || message; } catch {}
    const error = new Error(message);
    error.status = response.status;
    if (response.status === 401 && path !== '/auth/login' && typeof window !== 'undefined') {
      window.dispatchEvent(new Event('auth:unauthorized'));
    }
    throw error;
  }
  return response;
}

export async function request(path, options = {}) {
  const response = await requestResponse(path, options);
  return response.json();
}

export { API_BASE_URL };
