import {createContext,useContext,useEffect,useRef,useState} from 'react';
import {runtimeConfig,clerkClient,openSignIn} from './pilot-auth';
import {api} from './api';
const Context=createContext({status:'demo',config:{mode:'demo'},account:null,user:null,refresh:async()=>{}});
export const useAuth=()=>useContext(Context);
export function AuthProvider({children}){
 const [state,setState]=useState({status:'loading',config:null,account:null,user:null,error:''});
 const generation=useRef(0);
 async function refresh(){const run=++generation.current;try{const config=await runtimeConfig();if(config.mode!=='clerk'){setState({status:'demo',config,account:null,user:null});return;}const clerk=await clerkClient();if(!clerk.session){if(run===generation.current)setState({status:'visitor',config,account:null,user:null});return;}const account=await api('/auth/me');if(run===generation.current)setState({status:'ready',config,account,user:clerk.user});}catch(e){if(run===generation.current)setState(s=>({...s,status:e.status===401?'expired':'error',account:null,user:null,error:e.message}));}}
 useEffect(()=>{let off,disposed=false;refresh().then(async()=>{const c=await runtimeConfig();if(c.mode==='clerk'&&!disposed){const clerk=await clerkClient();if(!disposed)off=clerk.addListener(()=>refresh());}}).catch(()=>{});const changed=()=>refresh();const completed=e=>{if(!e.detail)refresh();};addEventListener('fogwrite:queue',completed);const expired=()=>{generation.current++;setState(s=>({...s,status:'expired',account:null,user:null,error:'Your session expired. Sign in again to continue. Your draft is preserved.'}));};addEventListener('fogwrite:account',changed);addEventListener('fogwrite:unauthorized',expired);return()=>{disposed=true;generation.current++;off?.();removeEventListener('fogwrite:account',changed);removeEventListener('fogwrite:queue',completed);removeEventListener('fogwrite:unauthorized',expired);};},[]);
 async function signOut(){await(await clerkClient()).signOut();generation.current++;setState(s=>({...s,status:'visitor',account:null,user:null}));window.dispatchEvent(new Event('fogwrite:signed-out'));}
 return <Context.Provider value={{...state,refresh,signOut,retry:async()=>{const clerk=await clerkClient();await clerk?.session?.getToken({skipCache:true});await refresh();},signIn:openSignIn,needsConsent:state.status==='ready'&&state.account.consent_version!==state.config.privacy_version}}>{children}</Context.Provider>;
}
