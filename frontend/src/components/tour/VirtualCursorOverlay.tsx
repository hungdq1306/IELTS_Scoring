import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import type {TourRole,TourStep} from './steps';

type Box={x:number;y:number;width:number;height:number};
export function VirtualCursorOverlay({target,step,ready,missing,isAutoPlaying,currentStepIndex,activeRoleTour,total,next,back,onToggle,onClose}:{target:string;step:TourStep;ready:boolean;missing:boolean;isAutoPlaying:boolean;currentStepIndex:number;activeRoleTour:TourRole;total:number;next:()=>void;back:()=>void;onToggle:()=>void;onClose:()=>void}) {
 const [box,setBox]=useState<Box|null>(null),[pulse,setPulse]=useState(false),[size,setSize]=useState({w:innerWidth,h:innerHeight}),[cardHeight,setCardHeight]=useState(260);
 const card=useRef<HTMLDivElement>(null),last=useRef('');
 useEffect(()=>{
  let frame=0,el:HTMLElement|null=null;last.current='';
  const update=()=>{el=Array.from(document.querySelectorAll<HTMLElement>(`[data-tour="${target}"]`)).at(-1)||null;if(!el){setBox(null);return;}const r=el.getBoundingClientRect();const b={x:Math.max(8,r.left-8),y:Math.max(8,r.top-8),width:Math.min(innerWidth-16,r.width+16),height:Math.max(20,Math.min(innerWidth<600?Math.max(100,innerHeight-cardHeight-130):Math.max(220,innerHeight-340),Math.min(innerHeight-16,r.bottom+8)-Math.max(8,r.top-8)))};const key=JSON.stringify(b);if(last.current!==key){last.current=key;setBox(b);} };
  const queue=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(update);};
  const observer=new ResizeObserver(queue);el=Array.from(document.querySelectorAll<HTMLElement>(`[data-tour="${target}"]`)).at(-1)||null;if(el){observer.observe(el);el.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:el.getBoundingClientRect().height>180?'start':'center'});}queue();
  const resize=()=>{setSize({w:innerWidth,h:innerHeight});queue();};
  addEventListener('scroll',queue,true);addEventListener('resize',resize);const timer=setInterval(queue,100);
  return()=>{clearInterval(timer);observer.disconnect();cancelAnimationFrame(frame);removeEventListener('scroll',queue,true);removeEventListener('resize',resize);};
 },[target,ready,cardHeight]);
 useEffect(()=>{if(!box||!ready)return;setPulse(false);const timer=setTimeout(()=>{setPulse(true);const el=document.querySelector<HTMLElement>(`[data-tour="${target}"][data-tour-preview="click"]`);if(el?.closest('[data-tour-sandbox]'))el.click();},700);return()=>clearTimeout(timer);},[target,ready,!!box]);
 useLayoutEffect(()=>{const el=card.current;if(!el)return;const observer=new ResizeObserver(()=>setCardHeight(el.offsetHeight));observer.observe(el);return()=>observer.disconnect();},[]);
 useEffect(()=>{card.current?.querySelector<HTMLButtonElement>('[data-tour-next]')?.focus({preventScroll:true});},[currentStepIndex]);
 const width=Math.min(370,size.w-24),cx=box?Math.max(16,Math.min(size.w-22,box.x+box.width*.55)):size.w/2,cy=box?Math.min(size.h-24,box.y+Math.min(box.height*.5,100)):size.h/2;
 let x=12,y=size.h-cardHeight-12;
 if(box){const right=box.x+box.width+18,left=box.x-width-18;
  if(right+width<size.w-12){x=right;y=Math.max(12,Math.min(size.h-cardHeight-12,box.y));}
  else if(left>=12){x=left;y=Math.max(12,Math.min(size.h-cardHeight-12,box.y));}
  else{x=Math.max(12,Math.min(size.w-width-12,box.x));y=box.y+box.height+18+cardHeight<size.h?box.y+box.height+18:box.y-cardHeight-18>=12?box.y-cardHeight-18:size.h-cardHeight-12;}
 }
 return createPortal(<div className="tour-overlay" data-tour-active-target={target} lang="vi">
  {box?<><div className="tour-shade" style={{left:0,top:0,width:'100%',height:box.y}}/><div className="tour-shade" style={{left:0,top:box.y,width:box.x,height:box.height}}/><div className="tour-shade" style={{left:box.x+box.width,top:box.y,right:0,height:box.height}}/><div className="tour-shade" style={{left:0,top:box.y+box.height,width:'100%',bottom:0}}/><div className="tour-cutout" style={{left:box.x,top:box.y,width:box.width,height:box.height}}/></>:<div className="tour-shade" style={{inset:0}}/>}
  <div className="tour-cursor" aria-hidden="true" style={{opacity:box?1:0,transform:`translate3d(${cx}px,${cy}px,0)`}}>{pulse&&box&&<span key={target} className="tour-click-ring"/>}<svg width="31" height="38" viewBox="0 0 31 38"><path d="M3 2L27 23L16 24L12 35L3 2Z" fill="#0F766E" stroke="white" strokeWidth="2.3" strokeLinejoin="round"/></svg></div>
  <div ref={card} className="tour-step-card" role="dialog" aria-modal="true" aria-labelledby="tour-title" tabIndex={-1} style={{left:x,top:Math.max(12,y),width,maxHeight:size.h-24}} onKeyDown={e=>{if(e.key!=='Tab')return;const controls=[...e.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')];const first=controls[0],last=controls.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}}}>
   <div className="tour-card-top"><span>Bước {currentStepIndex+1}/{total} · {activeRoleTour==='student'?'Student Guide':'Teacher Guide'}</span><button className="tour-auto" aria-pressed={isAutoPlaying} onClick={onToggle}>{isAutoPlaying?'Ⅱ':'▶'} Auto-play</button></div>
   <div className="tour-progress" aria-hidden="true">{Array.from({length:total},(_,i)=><span key={i} className={i<=currentStepIndex?'done':''}/>)}</div>
   <h2 id="tour-title">{step.title}</h2><p>{step.body}</p>
   {!ready&&<small role="status">Đang tìm vị trí trên trang…</small>}{missing&&<small role="status">Chưa thấy mục này. Bạn vẫn có thể tiếp tục hoặc quay lại.</small>}
   <div className="tour-controls"><button onClick={back} disabled={!currentStepIndex}>Quay lại</button><button className="tour-next" data-tour-next onClick={next}>{currentStepIndex===total-1?'Hoàn tất':'Tiếp theo'} →</button></div>
   <button className="tour-skip" onClick={onClose}>Bỏ qua <kbd>ESC</kbd></button>
  </div>
 </div>,document.body);
}
