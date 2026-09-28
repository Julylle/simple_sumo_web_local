export function Header() {
  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark">M</div>
        <div>
          <strong>Model Simulation Platform</strong>
          <span>Scientific modelling workspace</span>
        </div>
      </div>
      <div className="top-actions">
        <span className="connection">
          <i /> Backend connected
        </span>
        <span className="engine">
          Engine <b>Python / RK4</b>
        </span>
        <button className="avatar" title="Local development">
          SW
        </button>
      </div>
    </header>
  );
}
