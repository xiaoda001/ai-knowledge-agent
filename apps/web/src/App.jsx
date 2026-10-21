import React, { useEffect, useState } from 'react';
import LoginForm from './components/LoginForm.jsx';
import WorkspacePage from './pages/WorkspacePage.jsx';
import { getCurrentUser, listKnowledgeBases, login } from './server/index.js';

const AUTH_STORAGE_KEY = 'enterprise-knowledge-session';

function removeSavedSession() {
  try { localStorage.removeItem(AUTH_STORAGE_KEY); } catch {}
}

function readSavedSession() {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw);
    if (!saved?.token || !Number.isFinite(saved.expiresAt)) {
      removeSavedSession();
      return null;
    }
    return saved;
  } catch {
    removeSavedSession();
    return null;
  }
}

export default function App() {
  const [session, setSession] = useState(null);
  const [notice, setNotice] = useState('');
  const [restoring, setRestoring] = useState(true);

  useEffect(() => {
    let active = true;
    const saved = readSavedSession();
    if (!saved) {
      setRestoring(false);
      return () => { active = false; };
    }
    if (saved.expiresAt <= Date.now()) {
      removeSavedSession();
      setNotice('登录已过期，请重新登录。');
      setRestoring(false);
      return () => { active = false; };
    }
    Promise.all([getCurrentUser(saved.token), listKnowledgeBases(saved.token)])
      .then(([user, knowledgeBases]) => {
        if (active) setSession({ token: saved.token, user, knowledgeBases });
      })
      .catch(error => {
        if (!active) return;
        if (error.status === 401) removeSavedSession();
        else setNotice('无法恢复登录状态，请检查服务连接后重试。');
      })
      .finally(() => { if (active) setRestoring(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    function handleUnauthorized() {
      removeSavedSession();
      setSession(null);
      setRestoring(false);
      setNotice('登录已过期，请重新登录。');
    }
    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('auth:unauthorized', handleUnauthorized);
  }, []);

  async function handleLogin(username, password) {
    setNotice('');
    try {
      const auth = await login(username, password);
      const [user, knowledgeBases] = await Promise.all([
        getCurrentUser(auth.access_token), listKnowledgeBases(auth.access_token),
      ]);
      const expiresIn = Number(auth.expires_in) || 24 * 60 * 60;
      try {
        localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({
          token: auth.access_token,
          expiresAt: Date.now() + expiresIn * 1000,
        }));
      } catch {
        setNotice('登录成功，但浏览器无法保存会话；刷新页面后需要重新登录。');
      }
      setSession({ token: auth.access_token, user, knowledgeBases });
      if (!knowledgeBases.length) setNotice('登录成功；当前账号尚未加入知识库');
    } catch (error) { setNotice(error.message); }
  }

  function handleLogout() {
    removeSavedSession();
    setSession(null);
    setNotice('已退出登录。');
  }

  return <main className={`shell${session ? ' authenticated' : ''}`}>
    <header className="app-header">
      <div className="brand-lockup">
        <div className="mark" aria-hidden="true">知</div>
        <div><p className="eyebrow">ENTERPRISE KNOWLEDGE</p><h1>企业知识库</h1></div>
      </div>
      <div className="header-actions">
        {session && <button type="button" className="top-logout" onClick={handleLogout}>退出登录</button>}
        <span className="status"><span className="status-dot" />自托管工作区</span>
      </div>
    </header>
    {session
      ? <><WorkspacePage token={session.token} user={session.user} knowledgeBases={session.knowledgeBases} />
        {notice && <p className="notice global-notice">{notice}</p>}</>
      : restoring
        ? <section className="card narrow session-loading" role="status">正在恢复登录状态…</section>
        : <LoginForm onLogin={handleLogin} notice={notice} />}
  </main>;
}
