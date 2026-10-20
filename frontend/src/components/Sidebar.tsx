import { t, useLanguage } from '../i18n';
export type WorkspaceTab = "simulation" | "auto-calibration" | "history" | "sumo" | "realtime-sumo";

interface SidebarProps {
  tab: WorkspaceTab;
  onTabChange: (tab: WorkspaceTab) => void;
}

export function Sidebar({ tab, onTabChange }: SidebarProps) {
  useLanguage();
  const pythonActive = tab !== "sumo" && tab !== "realtime-sumo";

  return (
    <aside className="sidebar">
      <nav className="nav-section model-navigation" aria-label={t("Models")}>
        <p>{t("MODELS")}</p>
        <ul className="model-menu">
          <li>
            <button className={"nav " + ((tab === "sumo" || tab === "realtime-sumo") ? "active" : "")} onClick={() => onTabChange("sumo")}>
              <span className="nav-icon" aria-hidden="true">S</span>SUMO
              {tab === "sumo" && <span className="active-dot" />}
            </button>
            <ul className="model-submenu" aria-label={t("SUMO pages")}>
              <li>
                <button className={"nav " + (tab === "sumo" ? "active" : "")}
                  aria-current={tab === "sumo" ? "page" : undefined} onClick={() => onTabChange("sumo")}> {t("Offline SUMO")} </button>
              </li>
              <li>
                <button className={"nav " + (tab === "realtime-sumo" ? "active" : "")} aria-current={tab === "realtime-sumo" ? "page" : undefined} onClick={() => onTabChange("realtime-sumo")}> {t("Real-time SUMO")} </button>
              </li>
            </ul>
          </li>
          <li>
            <button className={"nav " + (pythonActive ? "active" : "")} onClick={() => onTabChange("simulation")}>
              <span className="nav-icon" aria-hidden="true">&#8767;</span>Python ASM
              {pythonActive && <span className="active-dot" />}
            </button>
            <ul className="model-submenu" aria-label={t("Python ASM pages")}>
              <li>
                <button className={"nav " + (tab === "simulation" ? "active" : "")}
                  aria-current={tab === "simulation" ? "page" : undefined} onClick={() => onTabChange("simulation")}> {t("Simulation")} </button>
              </li>
              <li>
                <button className={"nav " + (tab === "auto-calibration" ? "active" : "")}
                  aria-current={tab === "auto-calibration" ? "page" : undefined} onClick={() => onTabChange("auto-calibration")}> {t("Auto-Calibration")} </button>
              </li>
            </ul>
          </li>
        </ul>
      </nav>
    </aside>
  );
}
