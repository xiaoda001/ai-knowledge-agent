import React, { useEffect, useState } from 'react';
import { createDepartment, deleteDepartment, listDepartments, updateDepartment } from '../server/index.js';
import Modal from './Modal.jsx';

export default function DepartmentPanel({ token, onNotice }) {
  const [departments, setDepartments] = useState([]);
  const [name, setName] = useState('');
  const [editingDepartment, setEditingDepartment] = useState(null);
  const [editName, setEditName] = useState('');
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try { setDepartments(await listDepartments(token)); }
    catch (error) { onNotice(error.message); }
  }

  useEffect(() => { refresh(); }, [token]);

  async function save(event) {
    event.preventDefault();
    const value = name.trim();
    if (!value || busy) return;
    setBusy(true);
    try {
      await createDepartment(value, token);
      setName('');
      await refresh();
      onNotice('部门已创建');
    } catch (error) { onNotice(error.message); }
    finally { setBusy(false); }
  }

  async function rename(event) {
    event.preventDefault();
    const value = editName.trim();
    if (!editingDepartment || !value || busy) return;
    setBusy(true);
    try {
      await updateDepartment(editingDepartment.id, value, token);
      setEditingDepartment(null);
      setEditName('');
      await refresh();
      onNotice('部门名称已更新');
    } catch (error) { onNotice(error.message); }
    finally { setBusy(false); }
  }

  function closeRename() {
    if (busy) return;
    setEditingDepartment(null);
    setEditName('');
  }

  async function remove(department) {
    if (!window.confirm(`删除部门“${department.name}”？已关联成员或文档的部门不能删除。`)) return;
    try {
      await deleteDepartment(department.id, token);
      await refresh();
      onNotice('部门已删除');
    } catch (error) { onNotice(error.message); }
  }

  return <div className="panel-stack">
    <section className="card">
      <div className="section-title"><div><h3>部门目录</h3><p className="muted">成员和文档使用同一部门记录；重命名不会改变已有 ACL 关联。</p></div></div>
      <form className="row" onSubmit={save}>
        <label>部门名称<input value={name} onChange={event => setName(event.target.value)} maxLength="128" required /></label>
        <div className="form-actions"><button disabled={busy}>{busy ? '创建中…' : '创建部门'}</button></div>
      </form>
    </section>
    <Modal open={Boolean(editingDepartment)} title="重命名部门" onClose={closeRename}>
      <form onSubmit={rename}>
        <label>部门名称<input autoFocus value={editName} onChange={event => setEditName(event.target.value)} maxLength="128" required /></label>
        <div className="form-actions">
          <button disabled={busy || !editName.trim()}>{busy ? '保存中…' : '保存名称'}</button>
          <button type="button" className="secondary" disabled={busy} onClick={closeRename}>取消</button>
        </div>
      </form>
    </Modal>
    <section className="card">
      <div className="section-title"><div><h3>已登记部门</h3><p className="muted">删除仅适用于尚未关联账号或文档的部门。</p></div></div>
      {departments.length ? <div className="role-list">{departments.map(department => <article className="role-row" key={department.id}>
        <div className="role-copy"><strong>{department.name}</strong><p className="muted">目录 ID：{department.id}</p></div>
        <div className="form-actions"><button type="button" className="secondary" onClick={() => { setEditingDepartment(department); setEditName(department.name); }}>重命名</button>
          <button type="button" className="danger-button" onClick={() => remove(department)}>删除</button></div>
      </article>)}</div> : <p className="muted empty-list">还没有部门，请先创建部门。</p>}
    </section>
  </div>;
}
