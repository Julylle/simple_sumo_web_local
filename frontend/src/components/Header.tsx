import { t, useLanguage, setLanguage } from '../i18n';
export function Header({ engine = "Python" }: { engine?: string }) {
  const language = useLanguage();
  return (
    <header className="topbar">
      <div className="brand">
        {/* <div className="brand-mark">M</div>? */}
        <div>
          <strong>{t("Plant-wide model test")}</strong>
          <span>{t("Simplified modelling workspace")}</span>
        </div>
      </div>
      <div className="top-actions">
        <label className="language-picker">
          <span>{t(language === 'zh' ? '语言' : 'Language')}</span>
          <select aria-label={t("Language / 语言")} value={language} onChange={event => setLanguage(event.target.value === 'zh' ? 'zh' : 'en')}>
            <option value="en">{t("English")}</option>
            <option value="zh">中文</option>
          </select>
        </label>
        <span className="connection">
          <i /> {t("Backend connected")} </span>
        <span className="engine"> {t("Engine")} <b>{t(engine)}</b>
        </span>
        {/* <button className="avatar" title={t("Local development")}>
          Admin
        </button> */}
      </div>
    </header>
  );
}
