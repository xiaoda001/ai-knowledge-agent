import React, { useState } from 'react';

export default function LoginForm({ onLogin, notice }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  function submit(event) {
    event.preventDefault();
    onLogin(username, password);
  }

  return <section className="card narrow">
    <h2>登录</h2>
    <p className="muted">管理员账号由部署环境中的一次性 bootstrap 命令创建。</p>
    <form onSubmit={submit}>
      <label>用户名<input value={username} onChange={event => setUsername(event.target.value)} placeholder="测试账号: testadmin" required /></label>
      <label>密码<input type="password" value={password} onChange={event => setPassword(event.target.value)} placeholder="测试密码: testadmin" required /></label>
      <button>登录</button>
    </form>
    {notice && <p className="notice">{notice}</p>}
  </section>;
}
