import {createContext,useContext,useEffect,useRef,useState,type ReactNode} from 'react';
import {useAuth} from '../../auth-context';
import {tours,type TourRole,type TourStep} from './steps';
import {VirtualCursorOverlay} from './VirtualCursorOverlay';
import './tour.css';

type TourState={isOpen:boolean;activeRoleTour:TourRole;currentStepIndex:number;isAutoPlaying:boolean;isDemoSandboxActive:boolean;start:(role:TourRole)=>void;close:(completed?:boolean,accountChanged?:boolean)=>void;next:()=>void;back:()=>void;target:string;step:TourStep};
const Context=createContext<TourState|null>(null);
export const useTour=()=>{const state=useContext(Context);if(!state)throw new Error('TourProvider is required.');return state;};
const navigate=(route:string)=>{history.pushState({},'',route);dispatchEvent(new PopStateEvent('popstate'));};
export function TourProvider({children}:{children:ReactNode}) {
 const auth=useAuth(),userId=auth.status==='ready'?auth.account?.id:null;
 const [isOpen,setOpen]=useState(false),[activeRoleTour,setRole]=useState<TourRole>('student');
 const [currentStepIndex,setIndex]=useState(0),[isAutoPlaying,setAuto]=useState(true),[target,setTarget]=useState('');
 const [ready,setReady]=useState(false),[missing,setMissing]=useState(false),[chooser,setChooser]=useState(false);
 const origin=useRef(''),owner=useRef<string|null>(null),seen=useRef(new Set<string>()),queryHandled=useRef(false),returnFocus=useRef<HTMLElement|null>(null);
 const step=tours[activeRoleTour][currentStepIndex];
 function start(role:TourRole){
  if(!isOpen){const url=new URL(location.href);url.searchParams.delete('tour');origin.current=url.pathname+url.search+url.hash;returnFocus.current=document.activeElement as HTMLElement;}
  owner.current=userId;setRole(role);setIndex(0);setAuto(!matchMedia('(prefers-reduced-motion: reduce)').matches);setChooser(false);setOpen(true);
 }
 function close(completed=false,accountChanged=false){
  if(!accountChanged&&owner.current&&owner.current===userId){try{localStorage.setItem('fogwrite:tour_done:'+owner.current,completed?'completed':'skipped');}catch{}}
  setOpen(false);setReady(false);setTarget('');setChooser(false);
  navigate(origin.current||'/');requestAnimationFrame(()=>returnFocus.current?.isConnected&&returnFocus.current.focus());
 }
 function next(){setAuto(false);if(currentStepIndex===tours[activeRoleTour].length-1)close(true);else setIndex(i=>i+1);}
 function back(){setAuto(false);setIndex(i=>Math.max(0,i-1));}
 useEffect(()=>{
  if(auth.status==='loading')return;
  if(!queryHandled.current){queryHandled.current=true;const q=new URLSearchParams(location.search).get('tour');if(q==='student'||q==='teacher'){start(q);return;}}
  if(userId&&!auth.needsConsent&&!isOpen&&!seen.current.has(userId)){
   seen.current.add(userId);let done=false;try{done=!!localStorage.getItem('fogwrite:tour_done:'+userId);}catch{}
   if(!done&&!isOpen)start(['teacher','admin','ta'].includes(auth.account?.role)?'teacher':'student');
  }
 },[auth.status,userId,auth.needsConsent,isOpen]);
 useEffect(()=>{if(isOpen&&owner.current!==userId)close(false,true);},[userId]);
 useEffect(()=>{
  if(!isOpen)return;setReady(false);setMissing(false);setTarget(step.target);
  if(location.pathname!==step.route)navigate(step.route);
  let disposed=false,frame=0;
  const find=()=>{if(disposed)return;const el=Array.from(document.querySelectorAll<HTMLElement>(`[data-tour="${step.target}"]`)).at(-1);if(el&&el.getBoundingClientRect().width){disposed=true;observer.disconnect();clearTimeout(timeout);el.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:el.getBoundingClientRect().height>180?'start':'center'});setReady(true);} };
  const observer=new MutationObserver(()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(find);});observer.observe(document.body,{childList:true,subtree:true,attributes:true});
  const timeout=setTimeout(()=>{if(!disposed){disposed=true;observer.disconnect();setMissing(true);setReady(true);}},2500);frame=requestAnimationFrame(find);
  return()=>{disposed=true;observer.disconnect();clearTimeout(timeout);cancelAnimationFrame(frame);};
 },[isOpen,currentStepIndex,activeRoleTour]);
 useEffect(()=>{
  if(!isOpen||!ready)return;
  // Only move to sandbox controls; never click production controls or submit a form.
  const second=activeRoleTour==='student'&&currentStepIndex===3?'sample-error-highlight':activeRoleTour==='student'&&currentStepIndex===1?'tour-join-submit':activeRoleTour==='student'&&currentStepIndex===2?'sample-active-class':activeRoleTour==='student'&&currentStepIndex===4?'sample-drill-answer':activeRoleTour==='teacher'&&currentStepIndex===0?'teacher-invite-controls':activeRoleTour==='teacher'&&currentStepIndex===2?'teacher-score-override':null;
  if(!second)return;const timer=setTimeout(()=>setTarget(second),1500);
  const correction=activeRoleTour==='student'&&currentStepIndex===3?setTimeout(()=>setTarget('sample-correction-card'),2900):null;
  return()=>{clearTimeout(timer);if(correction)clearTimeout(correction);};
 },[isOpen,ready,currentStepIndex,activeRoleTour]);
 useEffect(()=>{
  if(!isOpen||!ready||!isAutoPlaying||document.hidden)return;
  const timer=setTimeout(()=>{if(currentStepIndex===tours[activeRoleTour].length-1)close(true);else setIndex(i=>i+1);},activeRoleTour==='student'&&currentStepIndex===3?6000:4500);
  return()=>clearTimeout(timer);
 },[isOpen,ready,isAutoPlaying,currentStepIndex,activeRoleTour]);
 useEffect(()=>{
  if(!isOpen)return;
  const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();close();}else if(e.key==='ArrowRight'&&!['INPUT','TEXTAREA','SELECT'].includes((e.target as HTMLElement).tagName)){e.preventDefault();next();}else if(e.key==='ArrowLeft'&&!['INPUT','TEXTAREA','SELECT'].includes((e.target as HTMLElement).tagName)){e.preventDefault();back();}};
  const pause=(e:Event)=>{if(e.isTrusted&&!(e.target as HTMLElement).closest('.tour-step-card'))setAuto(false);};
  document.addEventListener('keydown',key);document.addEventListener('pointerdown',pause,true);document.addEventListener('input',pause);
  const hidden=()=>{if(document.hidden)setAuto(false);};document.addEventListener('visibilitychange',hidden);
  return()=>{document.removeEventListener('keydown',key);document.removeEventListener('pointerdown',pause,true);document.removeEventListener('input',pause);document.removeEventListener('visibilitychange',hidden);};
 },[isOpen,currentStepIndex,activeRoleTour,userId]);
 const value={isOpen,activeRoleTour,currentStepIndex,isAutoPlaying,isDemoSandboxActive:isOpen,start,close,next,back,target,step};
 return <Context.Provider value={value}>{children}
  {!isOpen&&<div className="tour-launcher">{chooser&&<div className="tour-role-picker" aria-label="Chọn hướng dẫn"><button onClick={()=>start('student')}>Học sinh · 6 bước</button><button onClick={()=>start('teacher')}>Giáo viên · 4 bước</button><button onClick={()=>setChooser(false)}>Đóng</button></div>}<button className="tour-pill" aria-expanded={chooser} onClick={()=>setChooser(v=>!v)}>↗ Hướng dẫn sử dụng</button></div>}
  {isOpen&&<VirtualCursorOverlay {...{target,step,ready,missing,isAutoPlaying,currentStepIndex,activeRoleTour,next,back}} total={tours[activeRoleTour].length} onToggle={()=>setAuto(v=>!v)} onClose={()=>close()}/>}
 </Context.Provider>;
}
