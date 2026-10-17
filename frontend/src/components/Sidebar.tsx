export type WorkspaceTab = "simulation" | "auto-calibration" | "history" | "sumo";

interface SidebarProps {
  tab: WorkspaceTab;
  onTabChange: (tab: WorkspaceTab) => void;
}

export function Sidebar({ tab, onTabChange }: SidebarProps) {
  const pythonActive = tab !== "sumo";

  return (
    <aside className="sidebar">
      <nav className="nav-section model-navigation" aria-label="Models">
        <p>MODELS</p>
        <ul className="model-menu">
          <li>
            <button
              className={"nav " + (pythonActive ? "active" : "")}
              onClick={() => onTabChange("simulation")}
            >
              <span className="nav-icon" aria-hidden="true">&#8767;</span>Python ASM
              {pythonActive && <span className="active-dot" />}
            </button>
            <ul className="model-submenu" aria-label="Python ASM pages">
              <li>
                <button
                  className={"nav " + (tab === "simulation" ? "active" : "")}
                  aria-current={tab === "simulation" ? "page" : undefined}
                  onClick={() => onTabChange("simulation")}
                >
                  Simulation
                </button>
              </li>
              <li>
                <button
                  className={"nav " + (tab === "auto-calibration" ? "active" : "")}
                  aria-current={tab === "auto-calibration" ? "page" : undefined}
                  onClick={() => onTabChange("auto-calibration")}
                >
                  Auto-Calibration
                </button>
              </li>
            </ul>
          </li>
          <li>
            <button
              className={"nav " + (tab === "sumo" ? "active" : "")}
              aria-current={tab === "sumo" ? "page" : undefined}
              onClick={() => onTabChange("sumo")}
            >
              <span className="nav-icon" aria-hidden="true">S</span>Offline SUMO
              {tab === "sumo" && <span className="active-dot" />}
            </button>
          </li>
        </ul>
      </nav>
    </aside>
  );
}
