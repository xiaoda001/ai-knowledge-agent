import { request } from './httpClient.js';

export function listKnowledgeBases(token) {
  return request('/knowledge-bases', { token });
}

export function createKnowledgeBase(name, description, token) {
  const params = new URLSearchParams({ name, description });
  return request(`/knowledge-bases?${params}`, { token, method: 'POST' });
}

export function updateKnowledgeBase(knowledgeBaseId, knowledgeBase, token) {
  return request(`/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}`, {
    token, method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(knowledgeBase),
  });
}

export function deleteKnowledgeBase(knowledgeBaseId, token) {
  return request(`/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}`, { token, method: 'DELETE' });
}

export function classifyKnowledgeUpload(file, token) {
  const body = new FormData();
  body.append('file', file);
  return request('/knowledge-bases/classify-upload', { token, method: 'POST', body });
}

export function listMemberAccounts(token) {
  return request('/admin/users', { token });
}

export function createMember(user, token) {
  return request('/admin/users', {
    token,
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(user),
  });
}

export function addMemberToKnowledgeBase(knowledgeBaseId, userId, token) {
  return request(`/knowledge-bases/${knowledgeBaseId}/members/${userId}`, { token, method: 'POST' });
}

export function removeMemberFromKnowledgeBase(knowledgeBaseId, userId, token) {
  return request(`/knowledge-bases/${knowledgeBaseId}/members/${userId}`, { token, method: 'DELETE' });
}

export function listKnowledgeBaseMembers(knowledgeBaseId, token) {
  return request(`/knowledge-bases/${knowledgeBaseId}/members`, { token });
}

export function updateMemberRoles(userId, roleIds, token) {
  return request(`/admin/users/${userId}/roles`, { token, method: 'PUT',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ role_ids: roleIds }) });
}
