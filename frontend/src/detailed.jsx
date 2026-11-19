export const aspectGroups = {
  task_response: ["Relevance to Prompt", "Clarity of Position", "Depth of Ideas", "Appropriateness of Format", "Relevant & Specific Examples"],
  coherence_cohesion: ["Logical Organization", "Effective Introduction & Conclusion", "Supported Main Points", "Cohesive Devices Usage", "Paragraphing"],
  lexical_resource: ["Vocabulary Range", "Lexical Accuracy", "Spelling and Word Formation"],
  grammatical_range_accuracy: ["Sentence Structure Variety", "Grammar Accuracy", "Punctuation Usage"],
};

export function WritingChecks({ result }) {
  return <div className="writing-summary">
    <span><strong>{result.word_count}</strong> words</span>
    {result.paragraph_count != null && <span><strong>{result.paragraph_count}</strong> paragraphs</span>}
    <span>Task 2 target 250+ words</span>
  </div>;
}

export function AspectDiagnostics({ result, criterion }) {
  const items = result.aspect_reviews?.filter(item => aspectGroups[criterion].includes(item.aspect)) ?? [];
  if (!items.length) return null;
  return <div className="diagnostics"><h4>Writing diagnostics</h4>
    <dl className="aspect-list">{items.map(item =>
      <div key={item.aspect}><dt>{item.aspect} <strong>{item.score.toFixed(1)}</strong></dt><dd>{item.explanation}</dd></div>
    )}</dl>
  </div>;
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
