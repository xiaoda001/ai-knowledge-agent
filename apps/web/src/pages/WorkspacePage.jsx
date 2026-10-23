import React, { useEffect, useState } from 'react';
import ChatPanel from '../components/ChatPanel.jsx';
import KnowledgeBasePanel from '../components/KnowledgeBasePanel.jsx';
import MemberPanel from '../components/MemberPanel.jsx';
import RolesPanel from '../components/RolesPanel.jsx';
import DepartmentPanel from '../components/DepartmentPanel.jsx';
import { listDocuments, listRoles } from '../server/index.js';

const sections = [
  { id: 'chat', label: 'AI 聊天', description: '向已授权的知识库提问并查看来源，也可附加文件进行本轮问答。' },
  { id: 'knowledge', label: '知识库', description: '管理知识库成员与资料。' },
  { id: 'members', label: '成员', description: '管理成员账号、部门和角色。' },
  { id: 'roles', label: '角色', description: '创建角色，并配置角色可执行的功能权限。' },
  { id: 'departments', label: '部门', description: '维护部门目录；成员与文档通过目录关联部门。' },
];

function SectionIcon({ id }) {
  const paths = {
    chat: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v7a2.5 2.5 0 0 1-2.5 2.5H10l-4.5 3v-3.2A2.5 2.5 0 0 1 4 12.5z" /><path d="M8 8h8M8 11h5" /></>,
    knowledge: <><path d="M5 4.5A2.5 2.5 0 0 1 7.5 2H20v17H7.5A2.5 2.5 0 0 0 5 21z" /><path d="M5 4.5v14A2.5 2.5 0 0 1 7.5 16H20M9 6h7M9 9h7" /></>,
    members: <><circle cx="9" cy="8" r="3" /><path d="M3.5 19a5.5 5.5 0 0 1 11 0M16 5.5a3 3 0 0 1 0 5.8M17 14a5 5 0 0 1 3.5 4.8" /></>,
    roles: <><path d="M12 3 20.5 12 12 21 3.5 12z" /><circle cx="12" cy="12" r="2" /></>,
    departments: <><path d="M4 20V7l8-4 8 4v13M2 20h20" /><path d="M9 20v-5h6v5M8 9h.01M12 9h.01M16 9h.01" /></>,
  };
  return <svg className="side-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[id]}</svg>;
}

export default function WorkspacePage({ token, user, knowledgeBases }) {
  const [bases, setBases] = useState(knowledgeBases);
  const [knowledgeBaseId, setKnowledgeBaseId] = useState(knowledgeBases[0]?.id || '');
  const [documents, setDocuments] = useState([]);
  const [roles, setRoles] = useState([]);
  const [notice, setNotice] = useState('');
  const [activeSection, setActiveSection] = useState('chat');
  const permissions = user.permissions || [];
  const visibleSections = sections.filter(item => item.id === 'chat' ? permissions.includes('chat.use')
    : item.id === 'knowledge' ? ['document.read', 'document.upload', 'knowledge_base.create', 'knowledge_base.manage'].some(permission => permissions.includes(permission))
      : item.id === 'members' ? permissions.includes('member.manage')
      : item.id === 'roles' ? permissions.includes('role.manage')
      : item.id === 'departments' ? permissions.includes('department.manage')
          : true);
  const section = visibleSections.find(item => item.id === activeSection) || visibleSections[0] || sections[1];
  const selectedSectionId = section.id;

  async function refreshRoles() {
    try { setRoles(await listRoles(token)); }
    catch (error) { setNotice(error.message); }
  }

  async function refreshDocuments(id = knowledgeBaseId) {
    if (!id) return setDocuments([]);
    try { setDocuments(await listDocuments(id, token)); }
    catch { setDocuments([]); }
  }

  useEffect(() => { refreshDocuments(knowledgeBaseId); }, [knowledgeBaseId, token]);
  useEffect(() => { refreshRoles(); }, [token]);

  return <div className="workspace-layout">
    <aside className="workspace-sidebar">
      <p className="sidebar-label">工作区</p>
      <nav className="side-nav" aria-label="主菜单">
        {visibleSections.map(item => <button
          className={`side-nav-item${selectedSectionId === item.id ? ' active' : ''}`}
          type="button"
          key={item.id}
          aria-current={selectedSectionId === item.id ? 'page' : undefined}
          onClick={() => { setActiveSection(item.id); setNotice(''); }}
        >
          <SectionIcon id={item.id} />
          <span>{item.label}</span>
        </button>)}
      </nav>
      <div className="sidebar-account">
        <span className="account-avatar" aria-hidden="true">{(user.username || 'U').slice(0, 1).toUpperCase()}</span>
        <div className="account-copy">
          <strong>{user.username}</strong>
          <span>{user.is_admin ? '管理员' : '成员'}</span>
        </div>
        <span className="account-online" aria-label="在线" />
      </div>
    </aside>

    <section className={`workspace-main${section.id === 'chat' ? ' chat-active' : ''}`}
      aria-labelledby={section.id === 'chat' ? undefined : 'workspace-title'}
      aria-label={section.id === 'chat' ? section.label : undefined}>
      {section.id !== 'chat' && <div className="workspace-toolbar">
        <div className="page-heading">
          <h2 id="workspace-title">{section.label}</h2>
          <p>{section.description}</p>
        </div>
      </div>}

      {notice && <p className="notice workspace-notice" role="status">{notice}</p>}

      {section.id === 'chat' && <ChatPanel token={token} user={user} onNotice={setNotice} />}
      {section.id === 'knowledge' && <KnowledgeBasePanel
        token={token}
        user={user}
        roles={roles}
        knowledgeBases={bases}
        knowledgeBaseId={knowledgeBaseId}
        onKnowledgeBases={setBases}
        onKnowledgeBaseId={setKnowledgeBaseId}
        documents={documents}
        onRefreshDocuments={refreshDocuments}
        onNotice={setNotice}
      />}
      {section.id === 'members' && <MemberPanel
        token={token}
        user={user}
        roles={roles}
        knowledgeBaseId={knowledgeBaseId}
        onNotice={setNotice}
      />}
      {section.id === 'roles' && <RolesPanel token={token} roles={roles} onRolesChange={refreshRoles} onNotice={setNotice} />}
      {section.id === 'departments' && <DepartmentPanel token={token} onNotice={setNotice} />}

      <footer>答案仅来自当前用户有权访问的资料。无可用来源时，系统会说明未找到依据。</footer>
    </section>
  </div>;
}
