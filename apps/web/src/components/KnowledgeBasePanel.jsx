import React, { useEffect, useRef, useState } from 'react';
import { addMemberToKnowledgeBase, createKnowledgeBase, deleteKnowledgeBase,
  deleteDocument, expireDocument, getDocumentSource, getDocumentStatus, listKnowledgeBaseMembers, listMemberAccounts,
  removeMemberFromKnowledgeBase, updateKnowledgeBase, uploadMarkdown } from '../server/index.js';
import { listDocuments } from '../server/documents.js';
import Modal from './Modal.jsx';

export default function KnowledgeBasePanel({ token, user, knowledgeBases, knowledgeBaseId, onKnowledgeBases,
  onKnowledgeBaseId, onRefreshDocuments, onNotice }) {
  const canManage = user.permissions?.includes('knowledge_base.manage');
  const canManageMembers = user.permissions?.includes('member.manage');
  const canUpload = user.permissions?.includes('document.upload');
  const canRead = user.permissions?.includes('document.read');
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createDescription, setCreateDescription] = useState('');
  const [createMemberIds, setCreateMemberIds] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [editTarget, setEditTarget] = useState(null);
  const [membersTarget, setMembersTarget] = useState(null);
  const [members, setMembers] = useState([]);
  const [documentsOpen, setDocumentsOpen] = useState(false);
  const [documentItems, setDocumentItems] = useState([]);
  const [documentsBusy, setDocumentsBusy] = useState(false);
  const [preview, setPreview] = useState(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [uploadTarget, setUploadTarget] = useState(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    let active = true;
    if (!canManageMembers) return () => { active = false; };
    listMemberAccounts(token).then(items => { if (active) setAccounts(items); })
      .catch(error => { if (active) onNotice(error.message); });
    return () => { active = false; };
  }, [canManageMembers, token, onNotice]);

  async function submitCreate(event) {
    event.preventDefault();
    try {
      const created = await createKnowledgeBase(createName, createDescription, token);
      const added = [];
      for (const memberId of createMemberIds) {
        try { await addMemberToKnowledgeBase(created.id, memberId, token); added.push(memberId); }
        catch (error) { onNotice(`知识库已创建；部分成员添加失败：${error.message}`); }
      }
      onKnowledgeBases(items => [...items, created]);
      onKnowledgeBaseId(created.id);
      setCreateOpen(false);
      setCreateName(''); setCreateDescription(''); setCreateMemberIds([]);
      onNotice(added.length === createMemberIds.length ? '知识库已创建' : '知识库已创建，部分成员未能加入');
    } catch (error) { onNotice(error.message); }
  }

  async function submitEdit(event) {
    event.preventDefault();
    try {
      const updated = await updateKnowledgeBase(editTarget.id,
        { name: editTarget.name, description: editTarget.description }, token);
      onKnowledgeBases(items => items.map(item => item.id === updated.id ? { ...item, ...updated } : item));
      setEditTarget(null);
      onNotice('知识库信息已更新');
    } catch (error) { onNotice(error.message); }
  }

  async function openMembers(base) {
    setMembersTarget(base);
    try { setMembers(await listKnowledgeBaseMembers(base.id, token)); }
    catch (error) { setMembers([]); onNotice(error.message); }
  }

  async function changeMember(member, add) {
    if (!membersTarget) return;
    try {
      if (add) await addMemberToKnowledgeBase(membersTarget.id, member.id, token);
      else await removeMemberFromKnowledgeBase(membersTarget.id, member.id, token);
      setMembers(await listKnowledgeBaseMembers(membersTarget.id, token));
      if (!add && member.id === user.id) {
        const remaining = knowledgeBases.filter(base => base.id !== membersTarget.id);
        onKnowledgeBases(remaining);
        if (knowledgeBaseId === membersTarget.id) onKnowledgeBaseId(remaining[0]?.id || '');
        setMembersTarget(null);
      }
      onNotice(add ? `已添加成员：${member.username}` : `已移除成员：${member.username}`);
    } catch (error) { onNotice(error.message); }
  }

  async function removeKnowledgeBase(base) {
    if (!window.confirm(`删除知识库“${base.name}”？其中的文档、索引及相关数据也会删除。`)) return;
    try {
      await deleteKnowledgeBase(base.id, token);
      const remaining = knowledgeBases.filter(item => item.id !== base.id);
      onKnowledgeBases(remaining);
      if (knowledgeBaseId === base.id) onKnowledgeBaseId(remaining[0]?.id || '');
      onNotice('知识库已删除');
    } catch (error) { onNotice(error.message); }
  }

  async function openDocuments(base) {
    setDocumentsOpen(true);
    setDocumentsBusy(true);
    try {
      const items = await listDocuments(base.id, token);
      setDocumentItems(items);
      setUploadTarget(base);
    } catch (error) { setDocumentItems([]); onNotice(error.message); }
    finally { setDocumentsBusy(false); }
  }

  async function refreshDocumentList(base = uploadTarget) {
    if (!base) return;
    const items = await listDocuments(base.id, token);
    setDocumentItems(items);
    await onRefreshDocuments(base.id);
  }

  async function changeDocumentState(document, action) {
    const verb = action === 'expire' ? '标记为过期' : '永久删除';
    if (!window.confirm(`确定将“${document.filename}”${verb}吗？${action === 'delete' ? '原文件和索引也会删除。' : '过期文档将保留在列表中，但不再用于 AI 检索。'}`)) return;
    try {
      if (action === 'expire') await expireDocument(document.id, token);
      else await deleteDocument(document.id, token);
      await refreshDocumentList();
      onNotice(action === 'expire' ? '文档已标记为过期' : '文档及索引已删除');
    } catch (error) { onNotice(error.message); }
  }

  async function openPreview(document) {
    setPreview({ filename: document.filename, markdown: '' });
    setPreviewBusy(true);
    try { setPreview(await getDocumentSource(document.id, token)); }
    catch (error) { setPreview({ filename: document.filename, markdown: `无法预览：${error.message}` }); }
    finally { setPreviewBusy(false); }
  }

  async function uploadSelectedFile(file) {
    const base = uploadTarget;
    if (!base || !file) return;
    setUploading(true);
    try {
      const created = await uploadMarkdown(base.id, file, null, token);
      await refreshDocumentList(base);
      setUploading(false);
      onNotice(`已上传，正在索引：${file.name}`);
      for (let attempt = 0; attempt < 60; attempt++) {
        await new Promise(resolve => setTimeout(resolve, 2000));
        const status = await getDocumentStatus(created.id, token);
        if (status.status === 'ready' || status.status === 'failed') {
          if (knowledgeBaseId === base.id) await refreshDocumentList(base);
          onNotice(status.status === 'ready' ? `索引完成：${created.id}` : `索引失败：${status.error || '请检查 Worker 日志'}`);
          return;
        }
        onNotice(`资料“${file.name}”${status.status === 'processing' ? '处理中' : '排队中'}`);
      }
      onNotice(`资料“${file.name}”仍在处理，可稍后刷新列表`);
    } catch (error) { onNotice(error.message); }
    finally { setUploading(false); }
  }

  return <div className="panel-stack">
    <section className="card knowledge-table-card">
      <div className="section-title knowledge-list-heading">
        <div><h3>知识库列表</h3><p className="muted">集中管理知识库成员和资料。</p></div>
        {user.permissions?.includes('knowledge_base.create') && <button type="button" onClick={() => setCreateOpen(true)}>创建知识库</button>}
      </div>
      {knowledgeBases.length ? <div className="knowledge-table-wrap"><table className="knowledge-table">
        <thead><tr><th>知识库</th><th>描述</th><th>操作</th></tr></thead>
        <tbody>{knowledgeBases.map(base => <tr key={base.id} className={knowledgeBaseId === base.id ? 'selected' : ''}>
          <td><button type="button" className="knowledge-name-button" onClick={() => onKnowledgeBaseId(base.id)}>{base.name}</button></td>
          <td className="knowledge-description-cell">{base.description || <span className="muted">暂无描述</span>}</td>
          <td><div className="knowledge-actions">
            {canManage && <button type="button" className="secondary" onClick={() => setEditTarget({ ...base })}>编辑</button>}
            {canManageMembers && <button type="button" className="secondary" onClick={() => openMembers(base)}>成员</button>}
            {canRead && <button type="button" className="secondary" onClick={() => openDocuments(base)}>资料</button>}
            {canManage && <button type="button" className="danger-button" onClick={() => removeKnowledgeBase(base)}>删除</button>}
          </div></td>
        </tr>)}</tbody>
      </table></div> : <div className="empty-state knowledge-empty"><h3>还没有可用的知识库</h3><p className="muted">{user.permissions?.includes('knowledge_base.create') ? '创建知识库后即可添加成员和导入资料。' : '请联系管理员将你加入知识库。'}</p></div>}
    </section>

    <Modal open={createOpen} title="创建知识库" onClose={() => setCreateOpen(false)} className="wide-modal">
      <p className="muted modal-description">创建者会自动成为成员；也可以在此添加其他成员。</p>
      <form onSubmit={submitCreate}>
        <label>知识库名称<input autoFocus value={createName} onChange={event => setCreateName(event.target.value)} required maxLength="190" /></label>
        <label>知识库描述<textarea value={createDescription} onChange={event => setCreateDescription(event.target.value)} rows="3" maxLength="1000" /></label>
        {canManageMembers && <fieldset className="permission-fieldset"><legend>知识库成员</legend>
          {accounts.length ? <div className="permission-grid">{accounts.map(account => <label className="permission-option" key={account.id}>
            <input type="checkbox" checked={createMemberIds.includes(account.id)} onChange={() => setCreateMemberIds(ids => ids.includes(account.id) ? ids.filter(id => id !== account.id) : [...ids, account.id])} />
            <span><strong>{account.username}</strong><small>{account.roles.join('、') || '未分配角色'}</small></span>
          </label>)}</div> : <p className="muted">暂无可添加的成员账号。</p>}
        </fieldset>}
        <div className="form-actions modal-actions"><button>创建知识库</button><button type="button" className="secondary" onClick={() => setCreateOpen(false)}>取消</button></div>
      </form>
    </Modal>

    <Modal open={Boolean(editTarget)} title="编辑知识库" onClose={() => setEditTarget(null)}>
      {editTarget && <form onSubmit={submitEdit}>
        <label>知识库名称<input autoFocus value={editTarget.name} onChange={event => setEditTarget(item => ({ ...item, name: event.target.value }))} required maxLength="190" /></label>
        <label>知识库描述<textarea value={editTarget.description} onChange={event => setEditTarget(item => ({ ...item, description: event.target.value }))} rows="4" maxLength="1000" /></label>
        <div className="form-actions modal-actions"><button>保存修改</button><button type="button" className="secondary" onClick={() => setEditTarget(null)}>取消</button></div>
      </form>}
    </Modal>

    <Modal open={Boolean(membersTarget)} title={`${membersTarget?.name || ''} · 成员管理`} onClose={() => setMembersTarget(null)} className="wide-modal">
      <div className="member-manager-list">
        {members.map(member => <div className="member-manager-row" key={member.id}>
          <span><strong>{member.username}</strong><small>{member.roles.join('、') || '未分配角色'}</small></span>
          {canManageMembers && <button type="button" className="danger-button" onClick={() => changeMember(member, false)}>移除</button>}
        </div>)}
      </div>
      {canManageMembers && <fieldset className="permission-fieldset"><legend>添加成员</legend>
        {accounts.filter(account => !members.some(member => member.id === account.id)).length
          ? <div className="permission-grid">{accounts.filter(account => !members.some(member => member.id === account.id)).map(account => <label className="permission-option" key={account.id}>
            <input type="checkbox" onChange={event => { if (event.target.checked) changeMember(account, true); }} />
            <span><strong>{account.username}</strong><small>{account.roles.join('、') || '未分配角色'}</small></span>
          </label>)}</div> : <p className="muted">没有可添加的成员账号。</p>}
      </fieldset>}
    </Modal>

    <Modal open={documentsOpen} title={`${uploadTarget?.name || ''} · 资料`} onClose={() => { if (!uploading) setDocumentsOpen(false); }} className="wide-modal">
      <div className="section-title document-modal-toolbar"><p className="muted">知识库成员均可访问；过期资料保留记录但不参与 AI 检索。</p>
        {canUpload && <button type="button" disabled={uploading} onClick={() => fileInputRef.current?.click()}>{uploading ? '上传中…' : '添加资料'}</button>}</div>
      <input ref={fileInputRef} className="sr-only" type="file" accept=".pdf,.docx,.xlsx,.pptx,.txt,.md,.csv"
        onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; if (file) uploadSelectedFile(file); }} />
      {documentsBusy ? <p className="muted">正在加载文档…</p> : documentItems.length ? <div className="document-list">{documentItems.map(document => <div className="document-row" key={document.id}>
        <button type="button" className="document-preview-button" disabled={!['ready', 'expired'].includes(document.status)} onClick={() => openPreview(document)}>{document.filename}<small>{['ready', 'expired'].includes(document.status) ? document.id : '索引完成后可预览'}</small></button>
        <span className={`tag ${document.status}`}>{({ queued: '排队中', processing: '处理中', ready: '可用', failed: '失败', expired: '已过期' })[document.status] || document.status}</span>
        {document.error && <small className="error">{document.error}</small>}
        {canUpload && <div className="document-row-actions">
          {document.status !== 'expired' && <button type="button" className="secondary" disabled={['queued', 'processing'].includes(document.status)} onClick={() => changeDocumentState(document, 'expire')}>过期</button>}
          <button type="button" className="danger-button" disabled={['queued', 'processing'].includes(document.status)} onClick={() => changeDocumentState(document, 'delete')}>删除</button>
        </div>}
      </div>)}</div> : <p className="muted empty-list">暂无资料</p>}
    </Modal>

    <Modal open={Boolean(preview)} title={preview?.filename || '文档预览'} onClose={() => setPreview(null)} className="wide-modal document-preview-modal">
      {previewBusy && <p className="muted">正在加载文档内容…</p>}
      {preview && <pre className="document-preview-content">{preview.markdown}</pre>}
    </Modal>

  </div>;
}
