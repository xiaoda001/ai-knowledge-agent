import { request } from './httpClient.js';

export function listRoles(token) {
  return request('/roles', { token });
}

export function listRolePermissions(token) {
  return request('/roles/permissions', { token });
}

export function createRole(payload, token) {
  return request('/roles', { token, method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
}

export function updateRole(id, payload, token) {
  return request(`/roles/${id}`, { token, method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
}
