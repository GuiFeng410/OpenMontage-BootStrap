export function BoardPlaceholder() {
  const id = window.location.pathname.replace(/^\/next\/p\//, "");
  const href = `/p/${id}${window.location.search}`;
  return (
    <div className="wrap" data-backlot-next="board-placeholder">
      <p>看板尚未迁入 React。请使用默认站。</p>
      <p>
        <a href={href}>{href}</a>
      </p>
    </div>
  );
}
