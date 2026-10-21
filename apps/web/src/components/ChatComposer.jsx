import React, { useRef, useState } from 'react';

export default function ChatComposer({ question, onQuestionChange, onSubmit, loading, creatingConversation,
  attachment, onSelectAttachment, onRemoveAttachment }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const attachmentInputRef = useRef(null);

  return <div className="composer-dock">
    <div className="composer-inner">
      <form className="chat-composer" onSubmit={event => { setMenuOpen(false); onSubmit(event); }}>
        <input ref={attachmentInputRef} className="sr-only" type="file"
          accept=".pdf,.docx,.xlsx,.pptx,.txt,.md,.csv" tabIndex={-1} disabled={loading || creatingConversation}
          onChange={event => { onSelectAttachment(event.target.files?.[0] || null); event.target.value = ''; }} />
        {attachment && <div className="chat-attachment-preview">
          <span className="attachment-file-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M7 3h7l5 5v12a1 1 0 0 1-1 1H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" /><path d="M14 3v5h5" /></svg></span>
          <span className="attachment-file-copy"><strong>{attachment.name}</strong><small>{(attachment.size / (1024 * 1024)).toFixed(2)} MiB · 本轮问答附件</small></span>
          <button type="button" className="attachment-remove" aria-label={`移除附件：${attachment.name}`}
            disabled={loading || creatingConversation} onClick={onRemoveAttachment}>×</button>
        </div>}
        <label className="sr-only" htmlFor="chat-question">输入问题</label>
        <textarea id="chat-question" value={question} onChange={event => onQuestionChange(event.target.value)}
          onKeyDown={event => {
            const nativeEvent = event.nativeEvent;
            if (event.key !== 'Enter' || event.shiftKey || nativeEvent.isComposing || nativeEvent.keyCode === 229) return;
            event.preventDefault();
            if (!loading && !creatingConversation) event.currentTarget.form?.requestSubmit();
          }} rows="2" placeholder="输入问题，按 Enter 发送，Shift+Enter 换行…" required />
        <div className="composer-footer">
          <div className="composer-tools">
            <div className="composer-add-group">
              <button type="button" className="composer-add-button" aria-label="添加内容" aria-expanded={menuOpen}
                disabled={loading || creatingConversation}
                onClick={() => setMenuOpen(open => !open)}>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
              </button>
              {menuOpen && <div className="composer-add-menu">
                <button type="button" className="composer-menu-item" disabled={loading || creatingConversation}
                  onClick={() => { setMenuOpen(false); attachmentInputRef.current?.click(); }}>
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h7l5 5v12a1 1 0 0 1-1 1H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" /><path d="M14 3v5h5" /></svg>
                  附加到本轮聊天
                </button>
              </div>}
            </div>
            <span className="composer-hint">支持 PDF、Office、TXT、CSV、MD，单个附件不超过 20 MiB；附件仅用于本轮</span>
          </div>
          <button className="send-button" aria-label={loading ? '正在处理' : '发送问题'}
            disabled={!question.trim() || loading || creatingConversation}>
            {loading ? <span className="send-spinner" aria-hidden="true" /> : <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m21 3-7.2 18-3.9-7.1L3 10zM10 13.9 21 3" /></svg>}
          </button>
        </div>
      </form>
    </div>
  </div>;
}
