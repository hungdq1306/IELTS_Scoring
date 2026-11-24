import {createContext,useContext,useEffect,useRef,useState} from 'react';
import {runtimeConfig,clerkClient,openSignIn} from './pilot-auth';
import {api} from './api';
const Context=createContext({status:'demo',config:{mode:'demo'},account:null,user:null,refresh:async()=>{}});
export const useAuth=()=>useContext(Context);
export function AuthProvider({children}){
 const [state,setState]=useState({status:'loading',config:null,account:null,user:null,error:''});
 const generation=useRef(0), refreshFlight=useRef(null), profileSyncs=useRef(new Map());
 async function refresh(){
  let clerk;try{clerk=await clerkClient();}catch(e){setState(s=>({...s,status:'error',account:null,user:null,error:e.message}));throw e;}
  const sessionKey=(clerk?.session?.id||'session')+':'+(clerk?.user?.id||'visitor');
  if(refreshFlight.current?.key===sessionKey)return refreshFlight.current.promise;
  const run=++generation.current;
  const promise=(async()=>{try{
   const config=await runtimeConfig();
   if(config.mode!=='clerk'){if(run===generation.current)setState({status:'demo',config,account:null,user:null});return null;}
   if(!clerk.session){if(run===generation.current)setState({status:'visitor',config,account:null,user:null});return null;}
   const profileUser=clerk.user;
   let account=await api('/auth/me');
   if(run!==generation.current)return null;
   const fullName=(profileUser?.fullName||[profileUser?.firstName,profileUser?.lastName].filter(Boolean).join(' ')||profileUser?.username||'').trim()||null;
   const email=(profileUser?.primaryEmailAddress?.emailAddress||profileUser?.emailAddresses?.[0]?.emailAddress||'').trim()||null;
   const payload={full_name:fullName,email};
   const signature=JSON.stringify(payload), syncKey=sessionKey+':'+signature;
   const nameMissing=payload.full_name&&!account.full_name;
   const emailMissing=payload.email&&!account.email;
   if((nameMissing||emailMissing)&&!profileSyncs.current.has(syncKey)){
    profileSyncs.current.set(syncKey,true);
    try{const synced=await api('/auth/me',{method:'PATCH',body:JSON.stringify(payload)});if(run!==generation.current)return null;account={...account,...synced};}catch{/* Display-only fallback cannot deny sign-in. */}
   }
   if(run===generation.current)setState({status:'ready',config,account,user:profileUser});
   return account;
  }catch(e){if(run===generation.current)setState(s=>({...s,status:e.status===401?'expired':'error',account:null,user:null,error:e.message}));throw e;}
  })();
  refreshFlight.current={key:sessionKey,promise};
  try{return await promise;}finally{if(refreshFlight.current?.promise===promise)refreshFlight.current=null;}
 }
 useEffect(()=>{let off,disposed=false;refresh().then(async()=>{const c=await runtimeConfig();if(c.mode==='clerk'&&!disposed){const clerk=await clerkClient();if(!disposed)off=clerk.addListener(()=>{refresh().catch(()=>{});});}}).catch(()=>{});const changed=()=>{refresh().catch(()=>{});};const completed=e=>{if(!e.detail)refresh().catch(()=>{});};addEventListener('fogwrite:queue',completed);const expired=()=>{generation.current++;refreshFlight.current=null;setState(s=>({...s,status:'expired',account:null,user:null,error:'Your session expired. Sign in again to continue. Your draft is preserved.'}));};addEventListener('fogwrite:account',changed);addEventListener('fogwrite:unauthorized',expired);return()=>{disposed=true;generation.current++;off?.();removeEventListener('fogwrite:account',changed);removeEventListener('fogwrite:queue',completed);removeEventListener('fogwrite:unauthorized',expired);};},[]);
 async function signOut(){await(await clerkClient()).signOut();generation.current++;refreshFlight.current=null;setState(s=>({...s,status:'visitor',account:null,user:null}));window.dispatchEvent(new Event('fogwrite:signed-out'));}
 return <Context.Provider value={{...state,refresh,signOut,retry:async()=>{const clerk=await clerkClient();await clerk?.session?.getToken({skipCache:true});await refresh();},signIn:openSignIn,needsConsent:state.status==='ready'&&state.account.consent_version!==state.config.privacy_version}}>{children}</Context.Provider>;
}
