import { t, useLanguage } from '../i18n';
export function Empty({ title, text }: { title: string; text: string }) {
  useLanguage();
  return (
    <div className="empty">
      <div>⌁</div>
      <b>{t(title)}</b>
      <span>{t(text)}</span>
    </div>
  );
}
export function Placeholder({ title, text }: { title: string; text: string }) {
  useLanguage();
  return (
    <section className="placeholder">
      <div className="placeholder-icon">▦</div>
      <h1>{t(title)}</h1>
      <p>{t(text)}</p>
      <span>{t("Planned module")}</span>
    </section>
  );
}
