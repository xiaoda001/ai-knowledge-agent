import React, { useEffect, useRef, useState } from 'react';
import { createConversation, deleteConversation, getConversation, listConversations, streamChat } from '../server/index.js';
import ChatComposer from './ChatComposer.jsx';

const sourceVersionLabels = {
  current: '当前版本', scheduled: '待生效', needs_review: '版本日期待确认',
  superseded: '旧版本 · 已被新版替代', expired: '旧版本 · 已过期',
};

function formatResponseDuration(seconds) {
  if (seconds < 60) return `${seconds.toFixed(1)} 秒`;
  const roundedSeconds = Math.round(seconds);
  return `${Math.floor(roundedSeconds / 60)} 分 ${String(roundedSeconds % 60).padStart(2, '0')} 秒`;
}

export default function ChatPanel({ token, user, onNotice }) {
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [conversationId, setConversationId] = useState('');
  const [historyOpen, setHistoryOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [creatingConversation, setCreatingConversation] = useState(false);
  const [chatAttachment, setChatAttachment] = useState(null);
  const transcriptRef = useRef(null);
  const measuredUsage = messages
    .filter(message => message.role === 'assistant' && message.usage)
    .map(message => message.usage);
  const conversationUsage = measuredUsage.length ? {
    inputTokens: measuredUsage.reduce((sum, item) => sum + (item.input_tokens || 0), 0),
    outputTokens: measuredUsage.reduce((sum, item) => sum + (item.output_tokens || 0), 0),
    totalTokens: measuredUsage.reduce((sum, item) => sum + (item.total_tokens || 0), 0),
    tokensEstimated: measuredUsage.some(item => item.tokens_estimated),
    pricingConfigured: measuredUsage.every(item => item.pricing_configured && item.cost_usd != null),
    costUsd: measuredUsage.reduce((sum, item) => sum + (item.cost_usd || 0), 0),
  } : null;

  useEffect(() => {
    listConversations(token).then(setConversations).catch(error => onNotice(error.message));
  }, [token]);

  useEffect(() => {
    if (transcriptRef.current) transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
  }, [messages]);

  async function submitQuestion(event) {
    event.preventDefault();
    const currentQuestion = question.trim();
    if (!currentQuestion || loading || creatingConversation) return;
    const attachmentForTurn = chatAttachment;
    const turnId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    let activeConversationId = conversationId;
    try {
      if (!activeConversationId) {
        const created = await createConversation(token);
        activeConversationId = created.id;
        setConversationId(created.id);
        setConversations(previous => [created, ...previous.filter(item => item.id !== created.id)]);
      }
    } catch (error) {
      onNotice(error.message);
      return;
    }
    setMessages(previous => [...previous,
      { id: `${turnId}-user`, role: 'user', content: currentQuestion,
        sources: attachmentForTurn ? [{ type: 'attachment', filename: attachmentForTurn.name }] : [] },
      { id: `${turnId}-assistant`, role: 'assistant', content: '', sources: [], failedKnowledgeBases: [],
        status: attachmentForTurn ? '正在读取附件…' : '正在识别问题类型…', loading: true },
    ]);
    setQuestion('');
    setLoading(true);
    onNotice('');
    try {
      let attachmentFailed = false;
      await streamChat({ question: currentQuestion,
        conversationId: activeConversationId, attachment: attachmentForTurn, token, handlers: {
        token: data => setMessages(previous => previous.map(message => {
          if (message.id !== `${turnId}-assistant`) return message;
          const content = message.content ? data.content : data.content.replace(/^\s+/, '');
          return { ...message, content: message.content + content, status: '' };
        })),
        status: data => setMessages(previous => previous.map(message => message.id === `${turnId}-assistant`
          ? { ...message, status: data.message || '' } : message)),
        sources: data => {
          setMessages(previous => previous.map(message => message.id === `${turnId}-assistant`
            ? { ...message, sources: data.sources || [], failedKnowledgeBases: data.failed_knowledge_bases || [] } : message));
        },
        usage: data => setMessages(previous => previous.map(message => message.id === `${turnId}-assistant`
          ? { ...message, usage: data } : message)),
        error: data => {
          attachmentFailed = true;
          onNotice(data.message || '请求暂时失败，请稍后重试。');
          setMessages(previous => previous.map(message => message.id === `${turnId}-assistant`
            ? { ...message, content: message.content || '暂时无法完成请求，请稍后重试。', status: '', error: true } : message));
        },
      } });
      if (attachmentForTurn && !attachmentFailed) setChatAttachment(null);
    } catch (error) {
      onNotice(error.message);
      setMessages(previous => previous.map(message => message.id === `${turnId}-assistant`
        ? { ...message, content: '暂时无法生成回复，请检查连接后重试。', error: true } : message));
    } finally {
      setLoading(false);
      setMessages(previous => previous.map(message => message.id === `${turnId}-assistant`
        ? { ...message, status: '', loading: false } : message));
      listConversations(token).then(setConversations).catch(() => {});
    }
  }

  async function startNewConversation() {
    if (loading || creatingConversation) return;
    setMessages([]);
    setConversationId('');
    setQuestion('');
    setChatAttachment(null);
    setHistoryOpen(false);
    onNotice('');
    setCreatingConversation(true);
    try {
      const created = await createConversation(token);
      setConversationId(created.id);
      setConversations(previous => [created, ...previous.filter(item => item.id !== created.id)]);
    } catch (error) {
      onNotice(error.message);
    } finally {
      setCreatingConversation(false);
    }
  }

  async function openConversation(id) {
    if (!id || loading || creatingConversation) return;
    try {
      const conversation = await getConversation(id, token);
      setConversationId(id);
      setMessages(conversation.messages.map(message => ({ ...message, failedKnowledgeBases: [] })));
      setChatAttachment(null);
      setHistoryOpen(false);
      onNotice('');
    } catch (error) { onNotice(error.message); }
  }

  async function removeConversation(id) {
    if (loading || creatingConversation) return;
    try {
      await deleteConversation(id, token);
      setConversations(previous => previous.filter(item => item.id !== id));
      if (conversationId === id) {
        setMessages([]);
        setConversationId('');
        setQuestion('');
        setChatAttachment(null);
      }
    } catch (error) { onNotice(error.message); }
  }

  function selectChatAttachment(file) {
    if (file && file.size > 20 * 1024 * 1024) {
      setChatAttachment(null);
      onNotice('聊天附件不能超过 20 MiB。');
      return;
    }
    setChatAttachment(file);
    onNotice('');
  }

  return <section className="chat-workspace">
    <div className="conversation-toolbar">
      <div className="conversation-history">
        <button type="button" className="history-button" aria-expanded={historyOpen}
          aria-controls="conversation-history-list" onClick={() => setHistoryOpen(open => !open)}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16M4 12h16M4 19h10" /></svg>
          <span>历史对话</span>
          <span className="history-count">{conversations.length}</span>
        </button>
        {historyOpen && <div className="conversation-history-popover" id="conversation-history-list" aria-label="历史对话列表">
          <div className="history-popover-heading">
            <strong>历史对话</strong>
            <span>{conversations.length} 条</span>
          </div>
          {conversations.length === 0 ? <p className="history-empty">还没有历史对话。发送第一条消息后会自动保存。</p>
            : <div className="conversation-list">
              {conversations.map(item => <div className={`conversation-list-row${conversationId === item.id ? ' selected' : ''}`} key={item.id}>
                <button type="button" className="conversation-open-button" onClick={() => openConversation(item.id)}>
                  <span className="conversation-title">{item.title || '新对话'}</span>
                  <span className="conversation-date">{item.updated_at ? new Date(item.updated_at).toLocaleString() : ''}</span>
                </button>
                <button type="button" className="conversation-delete-button" aria-label={`删除对话：${item.title || '新对话'}`}
                  onClick={() => removeConversation(item.id)}>删除</button>
              </div>)}
            </div>}
        </div>}
      </div>
      {conversationUsage && <div className="conversation-usage-summary" aria-label="本对话已统计用量">
        <span>{conversationUsage.tokensEstimated ? '约 ' : ''}{conversationUsage.totalTokens.toLocaleString()} tokens</span>
        {conversationUsage.pricingConfigured && <span>预估 ${conversationUsage.costUsd.toFixed(8)} USD</span>}
      </div>}
      <button type="button" className="start-conversation-button" disabled={loading || creatingConversation} onClick={startNewConversation}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
        {creatingConversation ? '正在创建…' : '新建会话'}
      </button>
    </div>
    <div className="chat-transcript" ref={transcriptRef} aria-live="polite" aria-busy={loading}>
      {messages.length === 0 ? <div className="chat-welcome">
        <div className="welcome-orb" aria-hidden="true"><svg viewBox="0 0 48 48" fill="none"><path d="M15 12h18a7 7 0 0 1 7 7v10a7 7 0 0 1-7 7h-5l-5 4v-4h-8a7 7 0 0 1-7-7V19a7 7 0 0 1 7-7Z" /><circle cx="19" cy="24" r="2" /><circle cx="29" cy="24" r="2" /><path d="M19 30h10" /></svg></div>
        <p className="welcome-kicker">知识库 AI 助手</p>
        <h2>你好，有什么可以帮到你？</h2>
      </div> : <div className="chat-thread">
        {messages.map(message => message.role === 'user'
          ? <div className="message-row user-message" key={message.id}>
            <div className="user-message-body">
              {message.sources?.filter(source => source.type === 'attachment').map(source => <div className="message-attachment" key={source.filename}>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h7l5 5v12a1 1 0 0 1-1 1H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" /><path d="M14 3v5h5" /></svg>
                <span>{source.filename}</span>
              </div>)}
              <div className="user-bubble">{message.content}</div>
            </div>
            <span className="user-avatar" aria-hidden="true">{(user.username || 'U').slice(0, 1).toUpperCase()}</span>
          </div>
          : <article className="message-row assistant-message" key={message.id}>
            <div className="assistant-avatar" aria-hidden="true">知</div>
            <div className="assistant-message-content">
              <span className="response-label">知识库助手</span>
              {message.content
                ? <div className={`assistant-bubble answer${message.error ? ' message-error' : ''}`}>{message.content}</div>
                : <div className="assistant-bubble typing-indicator" role="status" aria-label={message.status || '正在生成回答'}>
                  {message.status && <span className="typing-indicator-text">{message.status}</span>}<i /><i /><i />
                </div>}
              {message.usage && <div className="message-usage" aria-label="本轮回复信息">
                {message.usage && <span>{message.usage.tokens_estimated ? '约 ' : ''}{message.usage.total_tokens.toLocaleString()} tokens
                  （输入 {message.usage.input_tokens.toLocaleString()} / 输出 {message.usage.output_tokens.toLocaleString()}）</span>}
                {message.usage?.pricing_configured && message.usage.cost_usd != null &&
                  <span>预估成本 ${message.usage.cost_usd.toFixed(8)} USD</span>}
                {message.usage.response_duration_seconds != null && <span>回复用时 {formatResponseDuration(message.usage.response_duration_seconds)}</span>}
              </div>}
              {message.failedKnowledgeBases?.length > 0 && <p className="partial-results-notice" role="status">
                {message.failedKnowledgeBases.map(base => base.name).join('、')} 暂时无法检索；以下答案和来源仅来自成功检索的知识库。
              </p>}
              {message.sources?.length > 0 && <div className="sources"><h3>参考来源 <span>{message.sources.length}</span></h3>{message.sources.map((source, index) => <details key={source.chunk_id || `${source.type}-${source.filename || index}`}>
                <summary><span className="source-index">{String(source.source_number || index + 1).padStart(2, '0')}</span><span>{source.type === 'attachment'
                  ? `${source.filename} · 本轮附件` : <>{source.knowledge_base_name} · {source.filename || source.document_id} · {source.effective_date ? `生效 ${source.effective_date}` : '生效日期未识别'} · 段落 {source.ordinal + 1}{source.version_status && source.version_status !== 'current' && <span className={`tag version-${source.version_status}`}>{sourceVersionLabels[source.version_status] || '版本状态待确认'}</span>}</>}</span></summary>
                {source.text && <p>{source.text}</p>}
              </details>)}</div>}
            </div>
          </article>)}
      </div>}
    </div>
    <ChatComposer question={question} onQuestionChange={setQuestion} onSubmit={submitQuestion}
      loading={loading} creatingConversation={creatingConversation} attachment={chatAttachment}
      onSelectAttachment={selectChatAttachment} onRemoveAttachment={() => setChatAttachment(null)} />
  </section>;
}
