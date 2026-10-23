import React, { useEffect, useMemo, useState } from 'react';
import { createMember, deleteMember, listDepartments, listMemberAccounts, listRolePermissions, updateMember } from '../server/index.js';
import Modal from './Modal.jsx';

const emptyUser = { nickname: '', username: '', password: '', department_id: '', clearance: '24', role_id: '' };

export default function MemberPanel({ token, user, roles, onNotice }) {
  const [newUser, setNewUser] = useState(emptyUser);
  const [accounts, setAccounts] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [permissionLabels, setPermissionLabels] = useState({});
  const [search, setSearch] = useState('');
  const [saving, setSaving] = useState(false);
  const [removingId, setRemovingId] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingMember, setEditingMember] = useState(null);

  async function refreshAccounts() {
    try { setAccounts(await listMemberAccounts(token)); }
    catch (error) { onNotice(error.message); }
  }

  useEffect(() => { refreshAccounts(); }, [token]);
  useEffect(() => { listDepartments(token).then(setDepartments).catch(error => onNotice(error.message)); }, [token]);
  useEffect(() => {
    listRolePermissions(token).then(items => setPermissionLabels(Object.fromEntries(items.map(item => [item.key, item.label]))))
      .catch(error => onNotice(error.message));
  }, [token]);

  const filteredAccounts = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    if (!query) return accounts;
    return accounts.filter(account => `${account.nickname || ''} ${account.username}`.toLocaleLowerCase().includes(query));
  }, [accounts, search]);

  function openCreateModal() {
    setNewUser({ ...emptyUser });
    setEditingMember(null);
    setModalOpen(true);
  }

  function openEditModal(member) {
    setEditingMember(member);
    setModalOpen(true);
    setNewUser({
      nickname: member.nickname || member.username,
      username: member.username,
      password: '',
      department_id: member.department_id || '',
      clearance: String(member.clearance ?? 24),
      role_id: member.role_ids?.[0] || '',
    });
  }

  function closeModal() {
    if (saving) return;
    setModalOpen(false);
    setEditingMember(null);
    setNewUser(emptyUser);
  }

  async function submitMember(event) {
    event.preventDefault();
    if (!newUser.nickname.trim() || !newUser.username.trim() || !newUser.department_id || !newUser.role_id) return;
    if (!editingMember && newUser.password.length < 12) return onNotice('密码至少需要 12 位');
    if (editingMember && newUser.password && newUser.password.length < 12) return onNotice('新密码至少需要 12 位');
    setSaving(true);
    try {
      const payload = {
        nickname: newUser.nickname.trim(),
        username: newUser.username.trim(),
        password: newUser.password,
        department_id: newUser.department_id,
        clearance: Number(newUser.clearance),
        role_ids: [newUser.role_id],
      };
      if (editingMember) {
        await updateMember(editingMember.id, payload, token);
        onNotice(`已更新成员 ${payload.nickname}`);
      } else {
        await createMember(payload, token);
        onNotice(`已创建成员 ${payload.nickname}`);
      }
      setModalOpen(false);
      setEditingMember(null);
      setNewUser(emptyUser);
      await refreshAccounts();
    } catch (error) { onNotice(error.message); }
    finally { setSaving(false); }
  }

  async function removeMember(member) {
    const displayName = member.nickname || member.username;
    if (!window.confirm(`停用成员“${displayName}”（${member.username}）？该账号将无法登录，并会退出所有知识库。`)) return;
    setRemovingId(member.id);
    try {
      await deleteMember(member.id, token);
      await refreshAccounts();
      onNotice(`成员 ${displayName} 已停用`);
    } catch (error) { onNotice(error.message); }
    finally { setRemovingId(''); }
  }

  const selectedRole = roles.find(role => role.id === newUser.role_id);
  const effectivePermissions = [...new Set(selectedRole?.permissions || [])]
    .map(permission => permissionLabels[permission] || permission);

  if (!user.permissions?.includes('member.manage')) {
    return <section className="card empty-state">
      <h3>成员管理</h3>
      <p className="muted">请联系管理员为你的角色授予成员管理权限。</p>
    </section>;
  }

  return <div className="panel-stack">
    <section className="card">
      <div className="section-title">
        <div><h3>成员管理</h3><p className="muted">创建和维护账号、部门、密级上限与角色。</p></div>
        <button type="button" onClick={openCreateModal}>创建成员账号</button>
      </div>
      <Modal open={modalOpen} title={editingMember ? `编辑成员：${editingMember.nickname || editingMember.username}` : '创建成员账号'} onClose={closeModal} className="wide-modal">
        <form onSubmit={submitMember}>
          <div className="row">
            <label>昵称<input value={newUser.nickname} onChange={event => setNewUser({ ...newUser, nickname: event.target.value })} maxLength="128" required /></label>
            <label>账号<input value={newUser.username} onChange={event => setNewUser({ ...newUser, username: event.target.value })} maxLength="190" autoComplete="username" required /></label>
          </div>
          <div className="row">
            <label>密码<input type="password" value={newUser.password} onChange={event => setNewUser({ ...newUser, password: event.target.value })}
              minLength="12" autoComplete="new-password" required={!editingMember}
              placeholder={editingMember ? '留空则不修改密码' : '至少 12 位'} /></label>
            <label>密级上限<input type="number" min="0" value={newUser.clearance} onChange={event => setNewUser({ ...newUser, clearance: event.target.value })} required /></label>
          </div>
          <div className="row">
            <label>角色<select value={newUser.role_id} onChange={event => setNewUser({ ...newUser, role_id: event.target.value })} required>
              <option value="">选择角色</option>{roles.map(role => <option key={role.id} value={role.id}>{role.name}{role.is_system ? ' · 系统角色' : ''}</option>)}
            </select></label>
            <label>部门<select value={newUser.department_id} onChange={event => setNewUser({ ...newUser, department_id: event.target.value })} required>
              <option value="">选择部门</option>{departments.map(department => <option key={department.id} value={department.id}>{department.name}</option>)}
            </select></label>
          </div>
          {selectedRole && <p className="role-permission-preview">角色权限：{effectivePermissions.join('、') || '无功能权限'}</p>}
          {!roles.length && <p className="muted">暂无可选角色，请先在“角色”模块创建角色。</p>}
          {!departments.length && <p className="muted">暂无可选部门，请先在“部门”模块登记部门。</p>}
          <div className="form-actions">
            <button disabled={saving || !roles.length || !departments.length}>{saving ? '保存中…' : editingMember ? '保存修改' : '创建成员'}</button>
            <button type="button" className="secondary" disabled={saving} onClick={closeModal}>取消</button>
            <span className="muted">密码至少 12 位；编辑时留空表示不修改密码。</span>
          </div>
        </form>
      </Modal>
    </section>

    <section className="card">
      <div className="section-title account-directory-heading">
        <div><h3>成员账号</h3><p className="muted">管理成员昵称和账号；角色权限对账号全局生效。</p></div>
        <label className="account-search">搜索成员<input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="输入昵称或账号" /></label>
      </div>
      {filteredAccounts.length ? <div className="data-table-wrap">
        <table className="data-table member-table member-directory-table">
          <thead><tr><th scope="col">昵称</th><th scope="col">账号</th><th scope="col">操作</th></tr></thead>
          <tbody>{filteredAccounts.map(member => <tr key={member.id}>
            <th scope="row">{member.nickname || member.username}</th>
            <td>{member.username}</td>
            <td><div className="table-actions">
              <button type="button" className="secondary" onClick={() => openEditModal(member)}>编辑</button>
              <button type="button" className="danger-button" disabled={removingId === member.id}
                onClick={() => removeMember(member)}>{removingId === member.id ? '停用中…' : '删除'}</button>
            </div></td>
          </tr>)}</tbody>
        </table>
      </div> : <p className="muted empty-list">{search ? '没有匹配的成员账号。' : '暂无成员账号。'}</p>}
    </section>
  </div>;
}
