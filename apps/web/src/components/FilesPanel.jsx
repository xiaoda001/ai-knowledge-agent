import React, { useEffect, useMemo, useRef, useState } from 'react';
import { classifyKnowledgeUpload, downloadStoredFile, listFiles, uploadMarkdown, uploadStoredFile } from '../server/index.js';
import Modal from './Modal.jsx';

const REGULAR_ACCEPT = '.pdf,.docx,.xlsx,.pptx,.txt,.md,.csv,.png,.jpg,.jpeg';
const KNOWLEDGE_ACCEPT = '.pdf,.docx,.xlsx,.pptx,.txt,.md,.csv';

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function FilesPanel({ token, user, knowledgeBases, onNotice }) {
  const [files, setFiles] = useState([]);
  const [file, setFile] = useState(null);
  const [destination, setDestination] = useState('regular');
  const [knowledgeBaseId, setKnowledgeBaseId] = useState(knowledgeBases[0]?.id || '');
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [classification, setClassification] = useState(null);
  const [classificationStatus, setClassificationStatus] = useState('idle');
  const classificationRequest = useRef(0);
  const canUploadRegular = user.permissions?.includes('file.upload');
  const canUploadKnowledge = user.permissions?.includes('document.upload') && knowledgeBases.length > 0;
  const destinations = useMemo(() => [
    ...(canUploadRegular ? [{ id: 'regular', title: '常规文件', description: '仅存储和下载，不进入 AI 检索。' }] : []),
    ...(canUploadKnowledge ? [{ id: 'knowledge', title: '知识库资料', description: '上传后自动推荐知识库，后台处理后可用于 AI 检索。' }] : []),
  ], [canUploadRegular, canUploadKnowledge]);
  const selectedBase = knowledgeBases.find(base => base.id === knowledgeBaseId);

  async function refresh() {
    try { setFiles(await listFiles(token)); }
    catch (error) { onNotice(error.message); }
  }

  useEffect(() => { refresh(); }, [token]);
  useEffect(() => {
    if (!destinations.some(item => item.id === destination)) setDestination(destinations[0]?.id || 'regular');
  }, [destinations, destination]);
  useEffect(() => {
    if (!knowledgeBases.some(base => base.id === knowledgeBaseId)) setKnowledgeBaseId(knowledgeBases[0]?.id || '');
  }, [knowledgeBases, knowledgeBaseId]);

  function closeModal() {
    if (busy) return;
    setOpen(false);
    setFile(null);
    setClassification(null);
    setClassificationStatus('idle');
  }

  async function selectFile(nextFile) {
    setFile(nextFile);
    setClassification(null);
    if (destination !== 'knowledge' || !nextFile) { setClassificationStatus('idle'); return; }
    const requestId = ++classificationRequest.current;
    setClassificationStatus('loading');
    try {
      const result = await classifyKnowledgeUpload(nextFile, token);
      if (requestId !== classificationRequest.current) return;
      setClassification(result);
      if (result.recommendations?.[0]) setKnowledgeBaseId(result.recommendations[0].id);
      setClassificationStatus('done');
    } catch (error) {
      if (requestId !== classificationRequest.current) return;
      setClassificationStatus('manual');
      onNotice(`自动识别未完成，请手动选择知识库：${error.message}`);
    }
  }

  async function submit(event) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    try {
      if (destination === 'knowledge') {
        if (!knowledgeBaseId) throw new Error('请选择目标知识库');
        const created = await uploadMarkdown(knowledgeBaseId, file, null, token);
        onNotice(`知识库资料已进入索引队列：${created.id}`);
      } else {
        await uploadStoredFile(file, token);
        await refresh();
        onNotice('常规文件上传完成，可在文件列表中下载');
      }
      setOpen(false);
      setFile(null);
    } catch (error) { onNotice(error.message); }
    finally { setBusy(false); }
  }

  async function download(item) {
    try { await downloadStoredFile(item.id, item.filename, token); }
    catch (error) { onNotice(error.message); }
  }

  return <div className="panel-stack">
    <section className="card">
      <div className="section-title">
        <div><h3>文件</h3><p className="muted">常规文件只供存储和下载；知识库资料会进入检索索引。</p></div>
        {destinations.length > 0 && <button type="button" onClick={() => setOpen(true)}>上传文件</button>}
      </div>
      {files.length ? <div className="document-list file-list">
        {files.map(item => <div className="document-row file-row" key={item.id}>
          <span className="file-name">{item.filename}<small>{formatBytes(item.size_bytes)} · {new Date(item.created_at).toLocaleString()}</small></span>
          <button type="button" className="secondary" onClick={() => download(item)}>下载</button>
        </div>)}
      </div> : <p className="muted empty-list">暂无常规文件</p>}
    </section>

    <Modal open={open} title="上传文件" onClose={closeModal}>
      <p className="muted modal-description">选择文件用途后，系统会按对应权限处理。</p>
      <form onSubmit={submit}>
        {destinations.length > 1 && <fieldset className="permission-fieldset">
          <legend>文件用途</legend>
          <div className="file-destinations">{destinations.map(item => <label className="permission-option" key={item.id}>
            <input type="radio" name="destination" value={item.id} checked={destination === item.id} onChange={() => { setDestination(item.id); setFile(null); setClassification(null); setClassificationStatus('idle'); }} />
            <span><strong>{item.title}</strong><small>{item.description}</small></span>
          </label>)}</div>
        </fieldset>}
        {destination === 'knowledge' && <label>目标知识库
          <select value={knowledgeBaseId} onChange={event => setKnowledgeBaseId(event.target.value)} required>
            {knowledgeBases.map(base => <option key={base.id} value={base.id}>{base.name}</option>)}
          </select>
        </label>}
        <label>{destination === 'knowledge' ? '选择入库资料' : '选择文件'}
          <input key={destination} type="file" accept={destination === 'knowledge' ? KNOWLEDGE_ACCEPT : REGULAR_ACCEPT}
            onChange={event => selectFile(event.target.files?.[0] || null)} required />
        </label>
        {destination === 'knowledge' && classificationStatus === 'loading' && <p className="classification-note" role="status">正在根据文件内容匹配可访问的知识库…</p>}
        {destination === 'knowledge' && classificationStatus === 'done' && classification?.recommendations?.length > 0 && <div className={`classification-note ${classification.mode}`} role="status">
          <strong>{classification.mode === 'auto' ? '自动识别建议' : '识别结果不确定，请确认'}</strong>
          <span>推荐：{classification.recommendations.map(item => item.name).join('、')} · 当前目标：{selectedBase?.name || '请选择'}</span>
        </div>}
        {destination === 'knowledge' && classificationStatus === 'manual' && <p className="classification-note confirm" role="status">无法自动匹配，请手动选择知识库。</p>}
        {destination === 'regular'
          ? <p className="muted file-upload-hint">支持 PDF、Office、文本和图片格式，单个文件最大 20 MiB。文件仅上传者和管理员可查看。</p>
          : <p className="muted file-upload-hint">支持 PDF、Word、Excel、PowerPoint、TXT、CSV 和 Markdown，单个文件最大 20 MiB。知识库成员均可访问入库资料。</p>}
        <div className="form-actions modal-actions"><button disabled={busy || !file || (destination === 'knowledge' && classificationStatus === 'loading')}>{busy ? '正在上传…' : destination === 'knowledge' ? '确认知识库并入库' : '上传文件'}</button>
          <button type="button" className="secondary" disabled={busy} onClick={closeModal}>取消</button></div>
      </form>
    </Modal>
  </div>;
}
