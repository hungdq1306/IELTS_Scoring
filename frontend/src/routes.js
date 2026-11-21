const paths={landing:'/',overview:'/overview',topics:'/topics',write:'/practice',check:'/check',feedback:'/assessment',skills:'/skill-practice',history:'/history',classes:'/classes',join:'/join',profile:'/profile',admin:'/admin'};
export const criterionKeys=['task_response','coherence_cohesion','lexical_resource','grammatical_range_accuracy'];
export function pathFor(route,criterion=null){return route==='feedback'&&criterion?`/assessment/${criterion.replaceAll('_','-')}`:paths[route]||'/';}
export function readRoute(location){
  const legacy=location.hash?.slice(1);
  if(legacy&&Object.hasOwn(paths,legacy))return {route:legacy,criterion:null};
  const path=location.pathname.replace(/\/$/,'')||'/';
  const criterion=path.startsWith('/assessment/')?path.slice(12).replaceAll('-','_'):null;
  if(criterionKeys.includes(criterion))return {route:'feedback',criterion};
  return {route:Object.keys(paths).find(key=>paths[key]===path)||'unknown',criterion:null};
}
