import { request, requestResponse } from './httpClient.js';

export function listFiles(token) {
  return request('/files', { token });
}

export function uploadStoredFile(file, token) {
  const body = new FormData();
  body.append('file', file);
  return request('/files', { method: 'POST', token, body });
}

export async function downloadStoredFile(id, filename, token) {
  const response = await requestResponse(`/files/${encodeURIComponent(id)}/download`, { token });
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
