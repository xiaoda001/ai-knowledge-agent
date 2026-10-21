import React, { useEffect, useMemo, useState } from 'react';
import { addMemberToKnowledgeBase, createMember, listKnowledgeBaseMembers, listMemberAccounts, listRolePermissions, updateMemberRoles } from '../server/index.js';
import Modal from './Modal.jsx';

const emptyUser = { username: '', password: '', department_id: '', clearance: '0', role_ids: [] };

export default function MemberPanel({ token, user, roles, knowledgeBaseId, onNotice }) {
  const [newUser, setNewUser] = useState(emptyUser);
  const [accounts, setAccounts] = useState([]);
  const [permissionLabels, setPermissionLabels] = useState({});
  const [knowledgeBaseMemberIds, setKnowledgeBaseMemberIds] = useState(new Set());
  const [search, setSearch] = useState('');
  const [savingMemberId, setSavingMemberId] = useState('');
  const [joiningMemberId, setJoiningMemberId] = useState('');
  const [createOpen, setCreateOpen] = useState(false);

  function closeCreateModal() {
    setCreateOpen(false);
    setNewUser(emptyUser);
  }

  async function refreshAccounts() {
    try { setAccounts(await listMemberAccounts(token)); }
    catch (error) { onNotice(error.message); }
  }

  async function refreshKnowledgeBaseMembers() {
    if (!knowledgeBaseId) return setKnowledgeBaseMemberIds(new Set());
    try {
      const members = await listKnowledgeBaseMembers(knowledgeBaseId, token);
      setKnowledgeBaseMemberIds(new Set(members.map(member => member.id)));
    } catch (error) { onNotice(error.message); }
  }

  useEffect(() => { refreshAccounts(); }, [token]);
  useEffect(() => { refreshKnowledgeBaseMembers(); }, [knowledgeBaseId, token]);
  useEffect(() => {
    listRolePermissions(token).then(items => setPermissionLabels(Object.fromEntries(items.map(item => [item.key, item.label]))))
      .catch(error => onNotice(error.message));
  }, [token]);

  function effectivePermissions(roleIds) {
    const permissions = [...new Set(roles.filter(role => roleIds.includes(role.id)).flatMap(role => role.permissions || []))];
    return permissions.map(permission => permissionLabels[permission] || permission);
  }

  async function submitMember(event) {
    event.preventDefault();
    if (!newUser.role_ids.length) return;
    try {
      const created = await createMember({
        username: newUser.username,
        password: newUser.password,
        department_id: newUser.department_id,
        clearance: Number(newUser.clearance),
        role_ids: newUser.role_ids,
      }, token);
      setNewUser(emptyUser);
      setCreateOpen(false);
      await refreshAccounts();
      onNotice(`已创建账号 ${created.username}。可在下方将其加入当前知识库。`);
    } catch (error) { onNotice(error.message); }
  }

  async function saveMemberRoles(member) {
    if (!member.role_ids.length) return onNotice('成员至少需要一个角色');
    setSavingMemberId(member.id);
    try {
      await updateMemberRoles(member.id, member.role_ids, token);
      await refreshAccounts();
      onNotice(`已更新 ${member.username} 的角色；角色功能权限对该账号全局生效`);
    } catch (error) { onNotice(error.message); }
    finally { setSavingMemberId(''); }
  }

  async function joinKnowledgeBase(member) {
    if (!knowledgeBaseId) return;
    setJoiningMemberId(member.id);
    try {
      await addMemberToKnowledgeBase(knowledgeBaseId, member.id, token);
      await refreshKnowledgeBaseMembers();
      onNotice(`已将 ${member.username} 加入当前知识库`);
    } catch (error) { onNotice(error.message); }
    finally { setJoiningMemberId(''); }
  }

  const filteredAccounts = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    if (!query) return accounts;
    return accounts.filter(account => account.username.toLocaleLowerCase().includes(query));
  }, [accounts, search]);

  if (!user.permissions?.includes('member.manage')) {
    return <section className="card empty-state">
      <h3>成员管理</h3>
      <p className="muted">请联系管理员为你的角色授予成员管理权限。</p>
    </section>;
  }

  return <div className="panel-stack">
    <section className="card">
      <div className="section-title">
        <div><h3>成员管理</h3><p className="muted">账号必须分配角色；知识库成员关系可稍后单独设置。</p></div>
        <button type="button" onClick={() => setCreateOpen(true)}>创建成员账号</button>
      </div>
      <Modal open={createOpen} title="创建成员账号" onClose={closeCreateModal} className="wide-modal">
      <p className="muted modal-description">账号需要至少一个角色；知识库成员关系可稍后单独设置。</p>
      <form onSubmit={submitMember}>
        <div className="row">
          <label>用户名<input value={newUser.username} onChange={event => setNewUser({ ...newUser, username: event.target.value })} required /></label>
          <label>初始密码<input type="password" minLength="12" autoComplete="new-password" value={newUser.password} onChange={event => setNewUser({ ...newUser, password: event.target.value })} required /></label>
        </div>
        <div className="row">
          <label>部门 ID<input value={newUser.department_id} onChange={event => setNewUser({ ...newUser, department_id: event.target.value })} required /></label>
          <label>密级上限<input type="number" min="0" value={newUser.clearance} onChange={event => setNewUser({ ...newUser, clearance: event.target.value })} required /></label>
        </div>
        <fieldset className="permission-fieldset">
          <legend>必选角色</legend>
          {roles.length ? <div className="permission-grid">{roles.map(role => <label className="permission-option" key={role.id}>
            <input type="checkbox" checked={newUser.role_ids.includes(role.id)} onChange={() => setNewUser(current => ({ ...current,
              role_ids: current.role_ids.includes(role.id) ? current.role_ids.filter(item => item !== role.id) : [...current.role_ids, role.id] }))} />
            <span><strong>{role.name}{role.is_system ? ' · 系统角色' : ''}</strong><small>{role.description || `${role.permissions.length} 项功能权限`}</small></span>
          </label>)}</div> : <p className="muted">暂无可分配角色。请先在「角色」菜单创建角色。</p>}
        </fieldset>
        {newUser.role_ids.length > 0 && <p className="role-permission-preview">将授予：{effectivePermissions(newUser.role_ids).join('、') || '无功能权限'}</p>}
        <div className="form-actions"><button disabled={!newUser.role_ids.length}>创建成员账号</button>
          <button type="button" className="secondary" onClick={closeCreateModal}>取消</button>
          <span className="muted">至少选择一个角色；初始密码至少 12 位。创建后不自动加入知识库。</span></div>
      </form>
      </Modal>
    </section>

    <section className="card">
      <div className="section-title account-directory-heading">
        <div><h3>成员账号</h3><p className="muted">角色权限全局生效；知识库新资料对本库成员开放，历史资料保留原有访问规则。</p></div>
        <label className="account-search">搜索账号<input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="输入用户名" /></label>
      </div>
      {!knowledgeBaseId && <p className="muted">当前没有可管理的知识库；你仍可创建账号并稍后加入知识库。</p>}
      {filteredAccounts.length ? <div className="role-list">{filteredAccounts.map(member => {
        const isMember = knowledgeBaseMemberIds.has(member.id);
        return <article className="member-row" key={member.id}>
          <div className="member-heading"><div><strong>{member.username}</strong>
            <small>{!knowledgeBaseId ? '未选择知识库' : isMember ? '当前知识库成员' : '未加入当前知识库'}</small></div>
            {knowledgeBaseId && !isMember && <button type="button" className="secondary" disabled={joiningMemberId === member.id}
              onClick={() => joinKnowledgeBase(member)}>{joiningMemberId === member.id ? '加入中…' : '加入当前知识库'}</button>}
          </div>
          <div className="permission-grid">{roles.map(role => <label className="permission-option" key={role.id}>
            <input type="checkbox" checked={member.role_ids.includes(role.id)} disabled={savingMemberId === member.id}
              aria-label={`${member.username}：${role.name}${role.is_system ? '（系统只读角色定义不可修改）' : ''}`}
              onChange={() => setAccounts(current => current.map(item => item.id !== member.id ? item : ({ ...item,
                role_ids: item.role_ids.includes(role.id) ? item.role_ids.filter(id => id !== role.id) : [...item.role_ids, role.id] })))} />
            <span><strong>{role.name}{role.is_system ? ' · 系统角色' : ''}</strong><small>{role.description || `${role.permissions.length} 项功能权限`}</small></span>
          </label>)}</div>
          <p className="role-permission-preview">选中角色将生效：{effectivePermissions(member.role_ids).join('、') || '无功能权限'}</p>
          <div className="form-actions"><button type="button" className="secondary" disabled={savingMemberId === member.id || !member.role_ids.length}
            onClick={() => saveMemberRoles(member)}>{savingMemberId === member.id ? '保存中…' : '保存角色'}</button></div>
        </article>;
      })}</div> : <p className="muted empty-list">没有匹配的成员账号。</p>}
    </section>
  </div>;
}
