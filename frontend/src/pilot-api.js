import {sessionToken} from './pilot-auth';
const pause=(ms,signal)=>new Promise((resolve,reject)=>{
  if(signal?.aborted)return reject(new DOMException('Aborted','AbortError'));
  const abort=()=>{clearTimeout(timer);reject(new DOMException('Aborted','AbortError'));};
  const timer=setTimeout(()=>{signal?.removeEventListener('abort',abort);resolve();},ms);
  signal?.addEventListener('abort',abort,{once:true});
});
export async function pilotApi(path,options={}){
  const headers={'Content-Type':'application/json',...options.headers},token=await sessionToken();
  if(token)headers.Authorization='Bearer '+token;
  const method=options.method||'GET';let storageKey;
  if(method==='POST'&&['/writing/task2/evaluate','/submissions'].includes(path)){
    const data=JSON.parse(options.body||'{}');
    if(!data.class_id)throw new Error('Join or select an active class in My Classes before submitting.');
  }
  if(method==='POST'&&['/writing/task2/evaluate','/submissions'].includes(path)){
    const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(path+(options.body||'')+(window.Clerk?.user?.id||'')));
    storageKey='fogwrite.request.'+Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('');
    let key;try{key=sessionStorage.getItem(storageKey);}catch{}
    key=key||crypto.randomUUID();headers['Idempotency-Key']=key;try{sessionStorage.setItem(storageKey,key);}catch{}
  }
  let response;
  try{response=await fetch('/api'+path,{...options,headers,cache:'no-store'});}
  catch(e){if(e.name==='AbortError')throw e;throw new Error('The backend is unreachable. Your draft is preserved.');}
  const body=await response.json().catch(()=>null);
  if(!response.ok||body===null){
    if(response.status===401)window.dispatchEvent(new Event('fogwrite:unauthorized'));
    const detail=body?.detail;
    const error=new Error(Array.isArray(detail)?detail.map(item=>item.msg).join(' '):detail?.message||(typeof detail==='string'?detail:'Unexpected backend response.'));error.status=response.status;error.detail=detail;throw error;
  }
  if(storageKey&&response.status!==202)try{sessionStorage.removeItem(storageKey);}catch{}
  if(response.status===202&&body.poll_url){
    const deadline=Date.now()+25*60*1000;window.dispatchEvent(new CustomEvent('fogwrite:queue',{detail:body}));
    try{while(Date.now()<deadline){
      await pause(1200,options.signal);
      const state=await pilotApi(body.poll_url.replace(/^\/api/,''),{signal:options.signal});
      window.dispatchEvent(new CustomEvent('fogwrite:queue',{detail:state}));
      if(state.status==='COMPLETED'){if(storageKey)try{sessionStorage.removeItem(storageKey);}catch{}return state.result;}
      if(state.status==='FAILED'){
        if(storageKey)try{sessionStorage.removeItem(storageKey);}catch{}
        throw new Error('This operation could not finish ('+(state.error_code||'AI unavailable')+'). Your essay is preserved.');
      }
    }throw new Error('Your job is saved. Return to History or retry this submission to reconnect.');}
    finally{window.dispatchEvent(new CustomEvent('fogwrite:queue',{detail:null}));}
  }
  if(method==='GET'&&/^\/writing\/task2\/[^/]+\/submission$/.test(path)&&!body.grade&&body.status!=='FAILED'){
    const grade=await pilotApi('/submissions/'+encodeURIComponent(body.submission_id)+'/result',{signal:options.signal});
    return {...body,grade};
  }
  return body;
}
