import { requestResponse } from './httpClient.js';
import { readSse } from '../utils/readSse.js';

export function streamChat({ knowledgeBaseIds, question, conversationId, history = [], attachment, token, handlers }) {
  const payload = { knowledge_base_ids: knowledgeBaseIds, question, conversation_id: conversationId, history };
  if (attachment) {
    const body = new FormData();
    body.append('payload', JSON.stringify(payload));
    body.append('attachment', attachment, attachment.name);
    return requestResponse('/chat', { method: 'POST', token, body })
      .then(result => readSse(result, handlers));
  }
  const response = requestResponse('/chat', {
    method: 'POST',
    token,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return response.then(result => readSse(result, handlers));
}
