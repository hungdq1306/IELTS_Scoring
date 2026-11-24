export const aspectGroups = {
  task_response: ["Relevance to Prompt", "Clarity of Position", "Depth of Ideas", "Appropriateness of Format", "Relevant & Specific Examples"],
  coherence_cohesion: ["Logical Organization", "Effective Introduction & Conclusion", "Supported Main Points", "Cohesive Devices Usage", "Paragraphing"],
  lexical_resource: ["Vocabulary Range", "Lexical Accuracy", "Spelling and Word Formation"],
  grammatical_range_accuracy: ["Sentence Structure Variety", "Grammar Accuracy", "Punctuation Usage"],
};

export function diagnosticItems(reviews, criterion, parentBand) {
 const allowed=aspectGroups[criterion]||[];
 return (Array.isArray(reviews)?reviews:[]).filter(item=>item&&allowed.includes(item.aspect_name||item.aspect)).map((item,index)=>{
  const proposed=typeof item.score==='number'&&Number.isFinite(item.score)?item.score:null;
  const score=item.aspect_name&&proposed!==null&&Number.isFinite(parentBand)?Math.min(proposed,parentBand+.5,9):proposed;
  const raw_score=typeof item.raw_score==='number'?item.raw_score:(score!==proposed?proposed:undefined);
  return {...item,raw_score,name:item.aspect_name||item.aspect,score,index,needsWork:score===null||score<parentBand||score<7.5,
   strength:typeof item.strength_vi==='string'?item.strength_vi:null,
   weakness:typeof item.weakness_vi==='string'?item.weakness_vi:null,
   legacy:typeof item.explanation==='string'?item.explanation:null};
 }).sort((a,b)=>(a.score??Infinity)-(b.score??Infinity)||a.index-b.index);
}
