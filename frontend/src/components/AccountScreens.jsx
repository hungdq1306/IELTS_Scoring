import {useEffect,useRef,useState} from 'react';
import {ArrowLeft,ArrowRight,Copy,Users,Plus,Settings} from 'lucide-react';
import {api} from '../api';
import {useAuth} from '../auth-context';
import {resolveActiveClass} from '../fogwrite-model';
import {clerkClient} from '../pilot-auth';
import {Notice,Spinner} from '../shared';
import {identity} from './UserProfileMenu';

function ConfirmDialog({title,message,detail,confirmLabel='Confirm',busy=false,onCancel,onConfirm}){
 const ref=useRef(null);
 useEffect(()=>{if(ref.current&&!ref.current.open)ref.current.showModal();return()=>{if(ref.current?.open)ref.current.close();};},[]);
 return <dialog className="submit-dialog" ref={ref} onCancel={onCancel}>
  <h2>{title}</h2>
  <p>{message}</p>
  {detail&&<p className="confirm-detail">{detail}</p>}
  <div className="actions">
   <button type="button" className="secondary" disabled={busy} onClick={onCancel}>Cancel</button>
   <button type="button" className="primary" autoFocus disabled={busy} onClick={onConfirm}>{confirmLabel}</button>
  </div>
 </dialog>;
}

export function ConsentScreen(){const auth=useAuth(),[accepted,setAccepted]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');const guard=useRef(false);return <section className="consent-screen surface"><h1>Your privacy, your choice.</h1><p>Please review these conditions before using classroom assessment.</p><details open><summary>Privacy and participation conditions</summary><p>This service is for adults aged 18 or older. Essays, questions and practice answers are sent to Google Gemini. Do not include sensitive personal information. Assigned teachers and TAs can review class work. Writing is retained for {auth.config.retention_days} days while the service operates.</p><p>{auth.config.gemini_data_policy==='free_product_improvement'?'Gemini unpaid services may use submitted content for product improvement.':auth.config.gemini_data_policy==='paid_no_training'?'The administrator confirmed paid Gemini services under the applicable no-training terms.':'The administrator has not confirmed Gemini data-use terms. You may exit without accepting.'}</p><p>AI scores are practice estimates, not official IELTS results.</p></details><label className="consent-choice" htmlFor="consent-accept"><input id="consent-accept" name="accepted" type="checkbox" checked={accepted} onChange={e=>setAccepted(e.target.checked)} disabled={busy}/>I confirm that I am 18 or older and accept these privacy conditions.</label>{error&&<Notice error>{error}</Notice>}<div className="actions"><button className="secondary" disabled={busy} onClick={()=>auth.signOut().catch(e=>setError(e.message))}>Decline and sign out</button><button className="primary" disabled={!accepted||busy} onClick={async()=>{if(guard.current)return;guard.current=true;setBusy(true);setError('');try{await api('/auth/consent',{method:'POST',body:JSON.stringify({adult_confirmed:true,accepted_privacy:true})});await auth.refresh();}catch(e){setError(e.message);}finally{guard.current=false;setBusy(false);}}}>{busy?'Saving…':'Accept and continue'}<ArrowRight size={16}/></button></div></section>;}
export function ProfileScreen(){const auth=useAuth(),user=identity(auth.user);return <section className="account-page surface"><h1>My Profile</h1><h2>{user.name}</h2><p>{user.email}</p><span className="topic-badge">{auth.account.role}</span><p>Your role and classroom permissions are managed by your institution.</p><button className="primary" onClick={async()=>{(await clerkClient()).openUserProfile();}}><Settings size={17}/>Manage account</button></section>;}
export function ClassesScreen({go}) {
 const auth=useAuth(),staff=['ta','teacher','admin'].includes(auth.account?.role),manage=['teacher','admin'].includes(auth.account?.role);
 const [rooms,setRooms]=useState([]),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 const [name,setName]=useState(''),[code,setCode]=useState(()=>new URLSearchParams(location.search).get('code')||''),[selected,setSelected]=useState(null);
 const [members,setMembers]=useState([]),[essays,setEssays]=useState([]),[memberSearch,setMemberSearch]=useState(''),[pendingRemoval,setPendingRemoval]=useState(null),[pendingLeave,setPendingLeave]=useState(null),[activeClassId,setActiveClassId]=useState('');
 const guard=useRef(false),epoch=useRef(0);
 const canManage=room=>manage&&room?.can_manage===true;
 const formatDate=value=>value?new Date(value*1000).toLocaleString():'-';
 const memberLabel=m=>m.display_label||m.full_name||m.email||('User #'+m.user_id.slice(0,8));
 async function load(account=auth.account) {
  const run=epoch.current;
  const list=staff?(await api('/teacher/classes')).items:account?.classes||[];
  if(run!==epoch.current)return;
  setRooms(list);setActiveClassId(resolveActiveClass(account?.classes||[],auth.user?.id||'')?.id||'');
 }
 useEffect(()=>{const run=++epoch.current;setSelected(null);setMembers([]);setEssays([]);setMemberSearch('');setPendingLeave(null);setPendingRemoval(null);setRooms([]);setLoading(true);load().catch(e=>{if(run===epoch.current)setError(e.message);}).finally(()=>{if(run===epoch.current)setLoading(false);});return()=>{epoch.current++;};},[auth.account?.id]);
 async function run(fn) {
  if(guard.current)return;
  const current=epoch.current;guard.current=true;setBusy(true);setError('');setMessage('');
  try{await fn();const account=await auth.refresh();if(current===epoch.current)await load(account||auth.account);}
  catch(e){if(current===epoch.current){const available=e.detail?.available_at;setError(e.message+(available?' Available at '+new Date(available).toLocaleString():''));}}
  finally{guard.current=false;if(current===epoch.current)setBusy(false);}
 }
 async function detail(room) {
  const current=epoch.current;
  const [m,e]=await Promise.all([api(`/teacher/classes/${room.id}/students`),api(`/teacher/classes/${room.id}/submissions`)]);
  if(current!==epoch.current)return;
  setMemberSearch('');setSelected(room);setMembers(m.items);setEssays(e.items);
 }
 async function copy(value){await navigator.clipboard.writeText(value);setMessage('Invite copied.');}
 function choose(id){try{localStorage.setItem('fogwrite.class.'+auth.user.id,id);setActiveClassId(id);window.dispatchEvent(new Event('fogwrite:class-changed'));setMessage('Class selected for your next essay.');}catch{setError('Browser storage is unavailable.');}}
 const filteredMembers=members.filter(m=>[m.display_label,m.full_name,m.email,m.user_id].some(v=>v?.toLowerCase().includes(memberSearch.trim().toLowerCase())));
 return <>
  <div className="page-heading"><div><h1>{selected?selected.name:'My Classes'}</h1><p>{staff?'Organize classes and review your students writing.':'Join your teacher class and keep your writing together.'}</p></div>{selected&&<button className="secondary" onClick={()=>{setSelected(null);setMemberSearch('');}}><ArrowLeft size={16}/>All classes</button>}</div>
  {error&&<Notice error>{error}</Notice>}{message&&<Notice>{message}</Notice>}
  {loading?<Spinner>Loading classes.</Spinner>:selected?<>
   <section className="surface class-detail"><h2>Class members</h2>
    <label htmlFor="member-search">Search class members<input id="member-search" name="memberSearch" value={memberSearch} onChange={e=>setMemberSearch(e.target.value)} maxLength={200}/></label>
    {!filteredMembers.length&&<p>{memberSearch.trim()?'No matching class members.':'This class has no members.'}</p>}
    {filteredMembers.map(m=><div className="member-row" key={m.user_id}><span><strong>{memberLabel(m)}</strong>{m.name_source==='self_reported'&&<small>Self-reported name</small>}{m.email&&<small className="member-email">{m.email}{m.email_source==='self_reported'?' (self-reported)':''}</small>}<small className="member-meta">{m.member_role||m.role} · {m.status||(m.active?'ACTIVE':'REMOVED')} · {m.submission_count??0} submissions · Joined {m.joined_at?new Date(m.joined_at*1000).toLocaleDateString():'-'}</small></span>{canManage(selected)&&m.active&&m.role==='student'&&<button className="secondary" disabled={busy} onClick={()=>setPendingRemoval(m)}>Remove student</button>}</div>)}
    {canManage(selected)&&<form onSubmit={e=>{e.preventDefault();const fields=new FormData(e.currentTarget);run(async()=>{await api(`/teacher/classes/${selected.id}/assign-ta`,{method:'POST',body:JSON.stringify({user_id:fields.get('member'),role:'ta'})});await detail(selected);});}}><label htmlFor="assign-ta-member">Existing TA account reference<input id="assign-ta-member" name="member" required maxLength={36}/></label><button className="secondary" disabled={busy}>Assign TA</button></form>}
   </section>
   <section className="surface class-detail"><h2>Class writing</h2>{!essays.length&&<p>No essays have been submitted to this class yet.</p>}
    {essays.map(essay=><details key={essay.id}><summary><strong>{essay.student_name||'Student'}</strong>{essay.student_email&&<span> ({essay.student_email}{essay.email_source==='self_reported'?' - self-reported':''})</span>} · <span>{essay.submission_code||essay.id.slice(0,8).toUpperCase()}</span> · {formatDate(essay.submitted_at)} · {essay.prompt} · {essay.status}</summary>
     <p className="submission-meta">Student: {essay.student_name||'Student'} · ID: {essay.submission_code||essay.id.slice(0,8).toUpperCase()} · Submitted: {formatDate(essay.submitted_at)}</p><p className="essay-text">{essay.essay}</p>{essay.grade&&<p>Estimated band: {essay.grade.estimated_overall_band}</p>}
     {canManage(selected)&&essay.grade&&<form onSubmit={e=>{e.preventDefault();const fields=new FormData(e.currentTarget);run(async()=>{await api(`/teacher/assessments/${essay.id}/override`,{method:'PATCH',body:JSON.stringify({scores:Object.fromEntries(['task_response','coherence_cohesion','lexical_resource','grammatical_range_accuracy'].map(key=>[key,Number(fields.get(key))])),reason:fields.get('reason')})});await detail(selected);});}}>
      {['task_response','coherence_cohesion','lexical_resource','grammatical_range_accuracy'].map(key=><label key={key} htmlFor={`override-${essay.id}-${key}`}>{key.replaceAll('_',' ')}<input id={`override-${essay.id}-${key}`} name={key} type="number" min="0" max="9" step="0.5" defaultValue={essay.grade.criterion_scores[key]} required/></label>)}
      <label htmlFor={`override-${essay.id}-reason`}>Reason for review<input id={`override-${essay.id}-reason`} name="reason" minLength={5} required/></label><button className="primary" disabled={busy}>Save reviewed scores</button>
     </form>}
    </details>)}
   </section>
  </>:<>
   {manage?<form className="surface classroom-form" onSubmit={e=>{e.preventDefault();if(!name.trim())return;run(async()=>{await api('/teacher/classes',{method:'POST',body:JSON.stringify({name:name.trim()})});setName('');setMessage('Class created.');});}}><label htmlFor="class-name">Create a class<input id="class-name" name="className" value={name} onChange={e=>setName(e.target.value)} required maxLength={120}/></label><button className="primary" disabled={busy||!name.trim()}><Plus size={17}/>Create Class</button></form>:!staff&&<>
    {!!rooms.length&&<Notice>You are currently enrolled in {rooms[0].name}. Please leave {rooms[0].name} before joining another class. <button type="button" className="text-button" onClick={()=>setPendingLeave(rooms[0])}>Leave current class</button></Notice>}
    <form className="surface classroom-form" onSubmit={e=>{e.preventDefault();run(async()=>{await api('/classes/join',{method:'POST',body:JSON.stringify({join_code:code.trim(),adult_confirmed:true,accepted_privacy:true})});setCode('');history.replaceState({},'','/classes');setMessage('You joined the class.');});}}><label htmlFor="invite-code">Teacher invite code<input id="invite-code" name="joinCode" value={code} onChange={e=>setCode(e.target.value)} required minLength={8} maxLength={100} autoComplete="off"/></label><button className="primary" disabled={busy||code.trim().length<8||rooms.length>0}>Join Class<ArrowRight size={16}/></button></form>
   </>}
   {!rooms.length?<section className="surface empty-state"><Users size={32}/><h2>{manage?'Your first class starts here.':'A place for your writing.'}</h2><p>{manage?'Create your first class to organize your students.':'Enter an invite code from your teacher. Past essays and feedback remain in History.'}</p></section>:<div className="class-grid">{rooms.map(room=>{
    const isEnrolled=auth.account.classes.some(c=>c.id===room.id),isChosen=room.id===activeClassId;
    return <article className="surface class-card" key={room.id}>
     <div className="class-card-header"><h2>{room.name}</h2>{isEnrolled&&isChosen&&<span className="topic-badge active-class-badge">Active · Đang chọn</span>}{room.enrollment_open===false&&<span className="topic-badge amber">Enrollment locked</span>}</div>
     <p>{room.student_count!=null?`${room.student_count} students`:room.role||'Class member'}{room.active===false?' · Inactive':''}</p>
     {!staff&&<div className="class-meta-list"><p>Teacher: <strong>{room.teacher_name||'Assigned teacher'}</strong></p><p>Daily credit limit: <strong>{room.daily_student_quota??3} credits/day</strong></p><p>Your submissions: <strong>{room.submission_count??0} essays</strong></p></div>}
     {canManage(room)&&<>
      <div className="invite-code"><code>{room.join_code||'Invite unavailable'}</code><button className="secondary" aria-label={`Copy invite code for ${room.name}`} disabled={busy||!room.join_code} onClick={()=>run(()=>copy(room.join_code))}><Copy size={16}/>Copy</button><button className="text-button" disabled={busy||!room.join_code} onClick={()=>run(()=>copy(location.origin+'/join?code='+encodeURIComponent(room.join_code)))}>Copy invite link</button><button className="text-button" disabled={busy} onClick={()=>{if(confirm('Replace the current invite code? Existing links will stop working.'))run(()=>api(`/teacher/classes/${room.id}/rotate-code`,{method:'POST'}));}}>Regenerate code</button></div>
      <form className="class-settings" key={room.name+':'+room.active+':'+room.daily_student_quota+':'+room.enrollment_open} onSubmit={e=>{e.preventDefault();const fields=new FormData(e.currentTarget);run(async()=>{await api(`/teacher/classes/${room.id}`,{method:'PATCH',body:JSON.stringify({name:fields.get('name').trim(),daily_student_quota:Number(fields.get('quota')),is_active:fields.get('active')==='on',enrollment_open:fields.get('enrollment')==='on'})});setSelected(null);setMessage('Class settings saved.');});}}>
       <label htmlFor={`class-name-${room.id}`}>Class name<input id={`class-name-${room.id}`} name="name" defaultValue={room.name} required maxLength={120}/></label><label htmlFor={`class-quota-${room.id}`}>Daily student credits<input id={`class-quota-${room.id}`} name="quota" type="number" min="1" max="100" defaultValue={room.daily_student_quota??3} required/></label><label className="consent-choice" htmlFor={`class-active-${room.id}`}><input id={`class-active-${room.id}`} name="active" type="checkbox" defaultChecked={room.active!==false}/>Class active</label><label className="consent-choice" htmlFor={`class-enrollment-${room.id}`}><input id={`class-enrollment-${room.id}`} name="enrollment" type="checkbox" defaultChecked={room.enrollment_open!==false}/>Allow new students to join (Enrollment open)</label><button className="secondary" disabled={busy}>Save class settings</button>
      </form>
     </>}
     <div className="actions">{staff&&<button className="primary" disabled={busy} onClick={()=>run(()=>detail(room))}>View class<ArrowRight size={16}/></button>}{room.active!==false&&isEnrolled&&<button className="secondary" disabled={isChosen} onClick={()=>choose(room.id)}>{isChosen?'Selected for next essay':'Use for my next essay'}</button>}{!staff&&<button type="button" className="secondary" disabled={busy} onClick={()=>setPendingLeave(room)}>Leave class</button>}{!staff&&isChosen&&go&&<button type="button" className="text-button" onClick={()=>go('check')}>Go to Check My Essay<ArrowRight size={14}/></button>}</div>
    </article>;
   })}</div>}
  </>}
  {pendingRemoval&&selected&&<ConfirmDialog title="Remove student from class?" message={`Remove ${memberLabel(pendingRemoval)} (${pendingRemoval.email||'no email'}) from ${selected.name}?`} confirmLabel="Remove student" busy={busy} onCancel={()=>setPendingRemoval(null)} onConfirm={()=>{const target=pendingRemoval;setPendingRemoval(null);run(async()=>{await api(`/teacher/classes/${selected.id}/students/${target.user_id}`,{method:'DELETE'});await detail(selected);});}}/>}
  {pendingLeave&&<ConfirmDialog title="Leave class?" message={`Leave ${pendingLeave.name}?`} detail="New AI essay submissions are disabled until you join another class. Existing essays, feedback and drills stay in History. Credits used today do not reset. You must wait 24 hours before joining a class again." confirmLabel="Leave class" busy={busy} onCancel={()=>setPendingLeave(null)} onConfirm={()=>{const room=pendingLeave;setPendingLeave(null);run(async()=>{await api(`/classes/${room.id}/leave`,{method:'POST'});try{localStorage.removeItem('fogwrite.class.'+auth.user.id);}catch{}setActiveClassId('');window.dispatchEvent(new Event('fogwrite:class-changed'));setMessage('You left the class. Your writing is preserved; the 24-hour join cooldown has started.');});}}/>}
 </>;
}
export {AdminScreen} from './AdminScreen';
