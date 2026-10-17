export function Header({ engine = "Python" }: { engine?: string }) {
  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark">M</div>
        <div>
          <strong>Activated Sludge Model Simulation</strong>
          <span>Scientific modelling workspace</span>
        </div>
      </div>
      <div className="top-actions">
        <span className="connection">
          <i /> Backend connected
        </span>
        <span className="engine">
          Engine <b>{engine}</b>
        </span>
        <button className="avatar" title="Local development">
          SW
        </button>
      </div>
    </header>
  );
}
