const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8022';

const API_ERROR_MESSAGES = {
  'Department is assigned to users or documents': '该部门仍关联着成员或文档，请先调整关联后再删除。',
  'Department name already exists': '部门名称已存在，请换一个名称。',
  'Department name cannot be blank': '部门名称不能为空。',
  'Department not found': '未找到该部门，可能已被删除，请刷新后重试。',
  'Select a department from the department directory': '请选择部门目录中已登记的部门。',
  'Department, classification, and access scope are required': '请填写部门、密级和访问范围。',
  'Username already exists': '账号已存在，请使用其他账号。',
  'Username, department, non-negative clearance, and 6-character password are required': '请填写账号、部门和密级上限；密码至少需要 6 位。',
  'Nickname, username, and department are required': '请填写昵称、账号和部门。',
  'Password must be at least 6 characters': '密码至少需要 6 位。',
  'Select roles from the role catalog': '请选择角色目录中的有效角色。',
  'Select a role from the role catalog': '请选择角色目录中的有效角色。',
  'You cannot assign permissions you do not have': '不能分配超出你自身权限范围的角色。',
  'You cannot grant permissions you do not have': '不能授予超出你自身权限范围的权限。',
  'User not found': '未找到该成员，可能已被删除或停用，请刷新后重试。',
  'You cannot deactivate your own account': '不能停用当前登录账号。',
  'Invalid credentials': '账号或密码错误。',
  'Invalid or expired token': '登录状态已失效，请重新登录。',
  'Administrator required': '此操作需要管理员权限。',
  'Role name is required': '请填写角色名称。',
  'This role name is reserved': '该角色名称为系统保留名称，请更换名称。',
  'Role name already exists': '角色名称已存在，请换一个名称。',
  'Role not found': '未找到该角色，可能已被删除，请刷新后重试。',
  'System roles cannot be changed': '系统角色不可修改。',
  'Knowledge base name already exists': '知识库名称已存在，请换一个名称。',
  'Knowledge base name cannot be blank': '知识库名称不能为空。',
  'Knowledge base not found': '未找到该知识库，可能已被删除或无权访问。',
  'Knowledge base or user not found': '未找到该知识库或成员账号。',
  'Knowledge base member not found': '该成员不在此知识库中。',
  'Knowledge base access denied': '无权访问该知识库。',
  'A knowledge base can have at most 50 memory notes': '每个知识库最多只能保存 50 条记忆。',
  'Memory title and content cannot be blank': '记忆标题和内容不能为空。',
  'Memory not found': '未找到该记忆，可能已被删除。',
  'Wait for document indexing to finish before deleting this knowledge base': '请等待知识库资料索引完成后再删除。',
  'Knowledge vectors could not be removed; knowledge base was kept': '知识向量删除失败，知识库已保留，请稍后重试。',
  'Document not found': '未找到该文档，可能已被删除。',
  'Wait for document indexing to finish before changing it': '请等待文档索引完成后再修改或删除。',
  'Document index could not be removed; document was kept': '文档索引删除失败，文档已保留，请稍后重试。',
  'Document version metadata could not be updated; retry later': '版本日期暂时无法同步到索引，请稍后重试。',
  'Document department and non-negative classification are required': '请填写文档所属部门和有效密级。',
  'Document ACL must stay within the uploader\'s department, clearance, and roles': '文档访问范围不能超出上传者的部门、密级和角色权限。',
  'Supported knowledge files: PDF, DOCX, XLSX, PPTX, TXT, CSV, MD': '支持的知识文件格式：PDF、DOCX、XLSX、PPTX、TXT、CSV、MD。',
  'Knowledge file exceeds 20 MiB': '知识文件不能超过 20 MiB。',
  'Filename must be at most 255 characters': '文件名不能超过 255 个字符。',
  'File exceeds 20 MiB': '文件不能超过 20 MiB。',
  'This file type is not supported': '不支持此文件格式。',
  'A filename of at most 255 characters is required': '请填写文件名，且文件名不能超过 255 个字符。',
  'Empty files cannot be uploaded': '不能上传空文件。',
  'File not found': '未找到该文件，可能已被删除。',
  'File content not found': '未找到文件内容，文件可能已被删除。',
  'No accessible knowledge base': '当前账号没有可访问的知识库。',
  'No text could be extracted from this file': '无法从文件中提取文字，请确认文件内容可读取。',
  'Document queue is unavailable': '文档处理服务暂不可用，请稍后重试。',
  'Missing chat request payload': '聊天请求内容缺失，请重新发送。',
  'Invalid chat request payload': '聊天请求格式无效，请检查输入后重试。',
  'Invalid chat attachment': '聊天附件无效，请重新选择文件。',
  'Conversation not found': '未找到该对话，可能已被删除。',
  'JWT_SECRET must be configured with at least 32 random bytes': '服务端登录密钥配置无效，请联系管理员。',
};

const FIELD_LABELS = {
  nickname: '昵称', username: '账号', password: '密码', department_id: '部门', clearance: '密级上限',
  role_ids: '角色', role_id: '角色', name: '名称', description: '说明', permissions: '权限',
  knowledge_base_ids: '知识库', knowledge_base_id: '知识库', question: '问题',
};

function localizeValidationErrors(detail) {
  if (!Array.isArray(detail)) return '';
  const messages = detail.map(issue => {
    const field = [...(issue.loc || [])].reverse().find(part => FIELD_LABELS[part]);
    const label = FIELD_LABELS[field] || '提交内容';
    if (issue.type === 'missing' || issue.type === 'string_too_short') return `请填写${label}。`;
    if (issue.type === 'greater_than_equal') return `${label}不能小于 ${issue.ctx?.ge ?? 0}。`;
    if (issue.type === 'string_too_long') return `${label}超出长度限制。`;
    return `请检查${label}的填写内容。`;
  });
  return [...new Set(messages)].join('');
}

function localizeApiError(detail, status) {
  if (typeof detail === 'string') {
    if (API_ERROR_MESSAGES[detail]) return API_ERROR_MESSAGES[detail];
    if (detail.startsWith('Unknown permissions:')) return `包含未知权限：${detail.slice('Unknown permissions:'.length).trim()}。`;
    if (detail.startsWith('Could not read document text:')) return '无法读取文档内容，请确认文件未损坏且包含可提取的文字。';
    if (/[\u3400-\u9fff]/.test(detail)) return detail;
  }
  const validationMessage = localizeValidationErrors(detail);
  if (validationMessage) return validationMessage;
  if (status === 401) return '登录状态已失效或账号密码错误，请检查后重试。';
  if (status === 403) return '权限不足，无法执行此操作。';
  if (status === 404) return '请求的内容不存在或已被删除。';
  if (status === 409) return '操作冲突，请检查名称是否重复或是否仍有关联数据。';
  if (status === 413) return '提交的文件过大，请缩小文件后重试。';
  if (status === 415) return '提交的文件格式不受支持。';
  if (status === 422) return '提交的信息不符合要求，请检查表单内容。';
  if (status >= 500) return '服务暂时不可用，请稍后重试。';
  return '操作失败，请检查输入后重试。';
}

export async function requestResponse(path, { token, headers = {}, ...options } = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
    });
  } catch {
    throw new Error('无法连接服务器，请检查网络或服务状态后重试。');
  }

  if (!response.ok) {
    let detail;
    try { detail = (await response.json()).detail; } catch {}
    const message = localizeApiError(detail, response.status);
    const error = new Error(message);
    error.status = response.status;
    if (response.status === 401 && path !== '/auth/login' && typeof window !== 'undefined') {
      window.dispatchEvent(new Event('auth:unauthorized'));
    }
    throw error;
  }
  return response;
}

export async function request(path, options = {}) {
  const response = await requestResponse(path, options);
  return response.json();
}

export { API_BASE_URL };
