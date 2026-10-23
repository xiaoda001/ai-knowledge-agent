import { request } from './httpClient.js';

export function listDepartments(token) {
  return request('/departments', { token });
}

export function createDepartment(name, token) {
  return request('/departments', { token, method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }) });
}

export function updateDepartment(id, name, token) {
  return request(`/departments/${encodeURIComponent(id)}`, { token, method: 'PUT',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) });
}

export function deleteDepartment(id, token) {
  return request(`/departments/${encodeURIComponent(id)}`, { token, method: 'DELETE' });
}
