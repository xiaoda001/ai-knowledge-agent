export async function readSse(response, handlers = {}) {
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { message = (await response.json()).detail || message; } catch {}
    throw new Error(message);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() || '';
    for (const eventText of events) {
      const event = eventText.match(/^event: (.+)$/m)?.[1];
      const raw = eventText.match(/^data: (.+)$/m)?.[1];
      if (raw && event) handlers[event]?.(JSON.parse(raw));
    }
  }
}
