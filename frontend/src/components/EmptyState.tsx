export function Empty({title,text}:{title:string;text:string}){return <div className="empty"><div>⌁</div><b>{title}</b><span>{text}</span></div>}
export function Placeholder({title,text}:{title:string;text:string}){return <section className="placeholder"><div className="placeholder-icon">▦</div><h1>{title}</h1><p>{text}</p><span>Planned module</span></section>}
