import { request } from './httpClient.js';

export function listDocuments(knowledgeBaseId, token) {
  return request(`/knowledge-bases/${knowledgeBaseId}/documents`, { token });
}

export function getDocumentStatus(documentId, token) {
  return request(`/documents/${documentId}/status`, { token });
}

export function getDocumentSource(documentId, token) {
  return request(`/documents/${encodeURIComponent(documentId)}/source`, { token });
}

export function expireDocument(documentId, token) {
  return request(`/documents/${encodeURIComponent(documentId)}/expire`, { token, method: 'POST' });
}

export function deleteDocument(documentId, token) {
  return request(`/documents/${encodeURIComponent(documentId)}`, { token, method: 'DELETE' });
}

export function uploadKnowledgeDocument(knowledgeBaseId, file, acl, token) {
  const body = new FormData();
  body.append('file', file);
  if (acl) {
    body.append('department_id', acl.departmentId);
    body.append('classification_level', acl.classificationLevel);
    body.append('allowed_roles', acl.allowedRoles.join(','));
  }
  return request(`/knowledge-bases/${knowledgeBaseId}/documents`, { token, method: 'POST', body });
}

export const uploadMarkdown = uploadKnowledgeDocument;
