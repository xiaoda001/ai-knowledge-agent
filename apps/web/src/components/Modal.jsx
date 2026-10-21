import React, { useEffect, useId, useRef } from 'react';

export default function Modal({ open, title, onClose, children, className = '' }) {
  const dialogRef = useRef(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    else if (!open && dialog.open) dialog.close();
  }, [open]);

  return <dialog ref={dialogRef} className={`app-modal ${className}`.trim()}
    aria-labelledby={titleId}
    onCancel={event => { event.preventDefault(); onClose(); }}
    onClick={event => { if (event.target === dialogRef.current) onClose(); }}>
    <div className="modal-heading">
      <h2 id={titleId}>{title}</h2>
      <button type="button" className="modal-close" aria-label="关闭弹窗" onClick={onClose}>×</button>
    </div>
    <div className="modal-content">{children}</div>
  </dialog>;
}
