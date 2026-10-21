import React, { useEffect, useState } from 'react';
import { createRole, listRolePermissions, updateRole } from '../server/index.js';
import Modal from './Modal.jsx';

const emptyRole = { name: '', description: '', permissions: [] };

export default function RolesPanel({ token, roles, onRolesChange, onNotice }) {
  const [permissionOptions, setPermissionOptions] = useState([]);
  const [draft, setDraft] = useState(emptyRole);
  const [editingId, setEditingId] = useState('');
  const [saving, setSaving] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    listRolePermissions(token).then(setPermissionOptions).catch(error => onNotice(error.message));
  }, [token]);

  function togglePermission(permission) {
    setDraft(current => ({ ...current, permissions: current.permissions.includes(permission)
      ? current.permissions.filter(item => item !== permission)
      : [...current.permissions, permission] }));
  }

  function editRole(role) {
    setEditingId(role.id);
    setDraft({ name: role.name, description: role.description || '', permissions: role.permissions || [] });
    setModalOpen(true);
  }

  function startCreate() {
    setEditingId('');
    setDraft(emptyRole);
    setModalOpen(true);
  }

  function closeModal() {
    if (saving) return;
    setModalOpen(false);
    setDraft(emptyRole);
    setEditingId('');
  }

  async function saveRole(event) {
    event.preventDefault();
    setSaving(true);
    try {
      if (editingId) await updateRole(editingId, { description: draft.description, permissions: draft.permissions }, token);
      else await createRole(draft, token);
      onRolesChange();
      setDraft(emptyRole);
      setEditingId('');
      setModalOpen(false);
      onNotice(editingId ? '角色权限已更新' : '角色已创建');
    } catch (error) { onNotice(error.message); }
    finally { setSaving(false); }
  }

  return <div className="panel-stack">
    <section className="card">
      <div className="section-title">
        <div><h3>角色管理</h3><p className="muted">配置角色可使用的功能权限。</p></div>
        <button type="button" onClick={startCreate}>创建角色</button>
      </div>
      <Modal open={modalOpen} title={editingId ? `配置角色：${draft.name}` : '创建角色'} onClose={closeModal} className="wide-modal">
        <p className="muted modal-description">勾选后，拥有该角色的成员即可使用对应功能。新资料按知识库成员共享；历史资料继续遵循原有访问规则。</p>
      <form onSubmit={saveRole}>
        {!editingId && <label>角色名称<input value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })} maxLength="128" required /></label>}
        <label>角色说明<input value={draft.description} onChange={event => setDraft({ ...draft, description: event.target.value })} maxLength="500" /></label>
        <fieldset className="permission-fieldset">
          <legend>功能权限</legend>
          <div className="permission-grid">
            {permissionOptions.map(item => <label className="permission-option" key={item.key}>
              <input type="checkbox" checked={draft.permissions.includes(item.key)} onChange={() => togglePermission(item.key)} />
              <span><strong>{item.label}</strong><small>{item.key}</small></span>
            </label>)}
          </div>
        </fieldset>
        <div className="form-actions"><button disabled={saving}>{saving ? '保存中…' : editingId ? '保存权限' : '创建角色'}</button>
          <button type="button" className="secondary" onClick={closeModal}>取消</button>
          <span className="muted">角色权限会立即影响已分配该角色的成员。</span></div>
      </form>
      </Modal>
    </section>

    <section className="card">
      <div className="section-title"><div><h3>角色列表</h3><p className="muted">成员可同时拥有多个角色，权限按并集生效。</p></div></div>
      {roles.length ? <div className="role-list">{roles.map(role => <article className="role-row" key={role.id}>
        <div className="role-copy"><strong>{role.name}</strong><p>{role.description || '未填写说明'}</p>
          <div className="role-tags">{(role.permissions || []).length ? role.permissions.map(permission => <span className="role-tag" key={permission}>{permissionOptions.find(item => item.key === permission)?.label || permission}</span>) : <span className="muted">未授予功能权限</span>}</div>
        </div>
        {role.is_system
          ? <span className="system-role-badge">系统角色 · 不可编辑</span>
          : <button type="button" className="secondary" onClick={() => editRole(role)}>配置</button>}
      </article>)}</div> : <p className="muted empty-list">还没有角色。创建角色后，可在成员表单中分配。</p>}
    </section>
  </div>;
}
