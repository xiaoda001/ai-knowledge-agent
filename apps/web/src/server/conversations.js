import { request } from './httpClient.js';

export const listConversations = token => request('/chat/conversations', { token });
export const createConversation = token => request('/chat/conversations', { method: 'POST', token });
export const getConversation = (id, token) => request(`/chat/conversations/${encodeURIComponent(id)}`, { token });
export const deleteConversation = (id, token) => request(`/chat/conversations/${encodeURIComponent(id)}`, { method: 'DELETE', token });
