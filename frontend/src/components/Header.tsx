import { t, useLanguage, setLanguage } from '../i18n';
export function Header({ engine = "Python" }: { engine?: string }) {
  const language = useLanguage();
  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark">M</div>
        <div>
          <strong>{t("Activated Sludge Model Simulation")}</strong>
          <span>{t("Scientific modelling workspace")}</span>
        </div>
      </div>
      <div className="top-actions">
        <label className="language-picker">
          <span>{language === 'zh' ? '语言' : 'Language'}</span>
          <select aria-label="Language / 语言" value={language} onChange={event => setLanguage(event.target.value === 'zh' ? 'zh' : 'en')}>
            <option value="en">English</option>
            <option value="zh">中文</option>
          </select>
        </label>
        <span className="connection">
          <i /> {t("Backend connected")} </span>
        <span className="engine"> {t("Engine")} <b>{t(engine)}</b>
        </span>
        <button className="avatar" title={t("Local development")}>
          SW
        </button>
      </div>
    </header>
  );
}
