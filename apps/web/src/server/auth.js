import { request } from './httpClient.js';

export function login(username, password) {
  const body = new URLSearchParams({ username, password });
  return request('/auth/login', { method: 'POST', body });
}

export function getCurrentUser(token) {
  return request('/auth/me', { token });
}
