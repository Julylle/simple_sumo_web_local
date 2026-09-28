export type WorkspaceTab = "simulation" | "comparison" | "history";

interface SidebarProps {
  tab: WorkspaceTab;
  onTabChange: (tab: WorkspaceTab) => void;
}

export function Sidebar({ tab, onTabChange }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="nav-section">
        <p>MODELS</p>
        <button className="nav active">
          <span className="nav-icon">∿</span>ODE Demo
          <span className="active-dot" />
        </button>
        <button className="nav disabled">
          <span className="nav-icon">A</span>ASM<span>Soon</span>
        </button>
        <button className="nav disabled">
          <span className="nav-icon">S</span>SUMO<span>Future</span>
        </button>
        <button className="nav disabled">
          <span className="nav-icon">C</span>CFD<span>Future</span>
        </button>
      </div>
      <div className="nav-section">
        <p>WORKSPACE</p>
        <button
          className={"nav " + (tab === "simulation" ? "active" : "")}
          onClick={() => onTabChange("simulation")}
        >
          <span className="nav-icon">▥</span>Simulation
        </button>
        <button
          className={"nav " + (tab === "comparison" ? "active" : "")}
          onClick={() => onTabChange("comparison")}
        >
          <span className="nav-icon">⇄</span>Comparison
        </button>
        <button
          className={"nav " + (tab === "history" ? "active" : "")}
          onClick={() => onTabChange("history")}
        >
          <span className="nav-icon">◷</span>Run history
        </button>
      </div>
      <div className="sidebar-bottom">
        <div className="security-note">
          <b>Protected execution</b>
          <span>Models and raw data remain server-side.</span>
        </div>
        <div className="version">MVP · ODE adapter</div>
      </div>
    </aside>
  );
}
