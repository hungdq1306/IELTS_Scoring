const topics = [
  ["Education", "Discussion", "Some people believe universities should focus on practical skills. Others believe academic knowledge is more important. Discuss both views and give your opinion."],
  ["Technology", "Opinion", "Some people believe that artificial intelligence will improve education. To what extent do you agree or disagree?"],
  ["Environment", "Problems & solutions", "Many cities are experiencing increasing air pollution. What are the causes, and what measures can be taken to address this problem?"],
  ["Society", "Discussion", "Some people prefer living in large cities, while others prefer small towns. Discuss both views and give your opinion."],
  ["Education", "Opinion", "Schools should teach financial literacy as a compulsory subject. To what extent do you agree or disagree?"],
  ["Work", "Advantages & disadvantages", "More people are working from home. Do the advantages of this development outweigh the disadvantages?"],
  ["Health", "Discussion", "Some people believe governments should be responsible for public health, while others believe individuals should take responsibility. Discuss both views and give your opinion."],
  ["Environment", "Opinion", "Governments should invest more in public transport than in building new roads. To what extent do you agree or disagree?"],
  ["Technology", "Advantages & disadvantages", "Children increasingly use digital devices for learning. Do the advantages outweigh the disadvantages?"],
  ["Society", "Two-part question", "Many young people move away from their hometowns after leaving school. Why does this happen? Is this a positive or negative development?"],
  ["Work", "Discussion", "Some people value job security, while others prefer a job they enjoy. Discuss both views and give your opinion."],
  ["Health", "Problems & solutions", "Many people do not get enough physical exercise. What are the reasons for this, and how could this situation be improved?"]
].map(([topic, type, prompt], i) => ({ id: i + 1, topic, type, prompt }));
function wordCount(text) {
  return text.match(/[\p{L}\p{N}]+(?:['’\-][\p{L}\p{N}]+)*/gu)?.length ?? 0;
}
function clock(seconds) {
  const n = Math.max(0, Math.floor(seconds));
  return `${Math.floor(n / 60).toString().padStart(2, "0")}:${(n % 60).toString().padStart(2, "0")}`;
}
function locateUnique(text, quote) {
  if (!quote) return null;
  const start = text.indexOf(quote);
  return start < 0 || text.indexOf(quote, start + 1) !== -1 ? null : { start, end: start + quote.length };
}
function annotations(result, essay, criterion) {
  const rows = [];
  const add = (item, kind, key, quote = item.original ?? item.quote) => {
    const range = locateUnique(essay, quote);
    if (range) rows.push({ ...item, ...range, quote, kind, criterion: key, id: `${kind}-${key}-${range.start}` });
  };
  if (!criterion || criterion === "grammatical_range_accuracy") (result.grammar_corrections ?? []).forEach((x) => add(x, "error", "grammatical_range_accuracy"));
  if (!criterion || criterion === "lexical_resource") (result.language_suggestions ?? []).forEach((x) => add(x, "suggestion", "lexical_resource"));
  Object.entries(result.criterion_feedback ?? {}).filter(([key]) => !criterion || criterion === key).forEach(([key, detail]) => (detail.evidence ?? []).forEach((x) => add(x, "evidence", key)));
  return rows.sort((a, b) => a.start - b.start || { error: 0, suggestion: 1, evidence: 2 }[a.kind] - { error: 0, suggestion: 1, evidence: 2 }[b.kind]);
}
export {
  annotations,
  clock,
  locateUnique,
  topics,
  wordCount
};
