import {diagnosticItems} from "./diagnostics-model";

export function AspectDiagnostics({ result, criterion }) {
 const items=diagnosticItems(result.aspect_reviews,criterion,result.criterion_scores?.[criterion]);
 return <section className="diagnostics" aria-label="Writing Diagnostics"><h3>Writing Diagnostics</h3>
 {!items.length&&<p className="diagnostics-unavailable">Bản lưu này chưa có chẩn đoán chi tiết theo khía cạnh.</p>}
 <div className="diagnostic-grid">{items.map((item,i)=><article className={`diagnostic-card ${item.needsWork?'needs-work':'strong'}`} key={item.name+'-'+i}>
  <header><h4>{item.name}</h4><span className="diagnostic-score">{item.score===null?'—':item.score.toFixed(1)}</span></header>
  <span className="diagnostic-status">{item.needsWork?'Cần cải thiện':'Điểm mạnh'}</span>
  {typeof item.raw_score==='number'&&item.raw_score!==item.score&&<p className="diagnostic-adjustment">Điểm khía cạnh được giới hạn theo band tiêu chí; model đề xuất {item.raw_score.toFixed(1)}.</p>}
  {item.strength||item.weakness?<><p><strong>Điểm tốt:</strong> {item.strength||'Bản lưu chưa có nhận xét riêng.'}</p><p><strong>Thiếu sót:</strong> {item.weakness||'Bản lưu chưa có nhận xét riêng.'}</p></>:<p>{item.legacy||'Bản lưu chưa có nhận xét chi tiết.'}</p>}
 </article>)}</div></section>;
}

export function ParagraphFeedback({ result, essay }) {
  const paragraphs = essay?.split(/\r?\n(?:[ \t]*\r?\n)+/).map(value => value.trim()).filter(Boolean) ?? [];
  if (!result.paragraph_reviews?.length) return <p className="muted">Paragraph feedback is unavailable in this saved assessment.</p>;
  return <div className="paragraph-reviews">{result.paragraph_reviews.map(item =>
    <article className="paragraph-card" key={item.paragraph_number}>
      <h3>Paragraph {item.paragraph_number}<span className="pill">{item.role}</span></h3>
      {paragraphs[item.paragraph_number - 1] && <details><summary>Read original paragraph</summary>
        <p className="essay-text">{paragraphs[item.paragraph_number - 1]}</p>
      </details>}
      <p>{item.summary}</p>
      {item.evidence && <blockquote><strong>"{item.evidence.quote}"</strong><p>{item.evidence.explanation}</p></blockquote>}
      <div className="next-step"><h4>Suggested improvement</h4><p>{item.improvement}</p></div>
    </article>
  )}</div>;
}

export function LanguageSuggestions({ result }) {
  return <section><h3>Optional language improvements</h3>
    {result.language_suggestions?.length ? result.language_suggestions.map((item, i) => <div className="correction" key={i}>
      <span className="pill">{item.category.replaceAll("_", " ")}</span>
      <div className="edit-pair"><div><small>Original wording</small><p>{item.original}</p></div>
        <div><small>Suggested wording</small><strong>{item.corrected}</strong></div></div>
      <p>{item.explanation}</p>
    </div>) : <p className="muted">No optional language changes returned.</p>}
  </section>;
}
