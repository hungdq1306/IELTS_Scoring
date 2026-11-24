import {useEffect,useRef,useState} from 'react';
import {useTour} from './TourProvider';
import {Shell,Overview,EssayEditor} from '../StudioScreens';
import {normalizeDraft} from '../../fogwrite-model';
import {TourSampleFeedbackModal} from './TourSampleFeedbackModal';
import {sampleExcerpt} from './sample-data';

const sampleEssay=`Universities play an important role in preparing young people for their future. Some people argue that these institutions should concentrate on practical skills, while others believe academic knowledge deserves greater attention. In my view, a balanced education gives students the strongest foundation for work and for lifelong learning.

${sampleExcerpt}

On the one hand, practical experience allows students to connect what they study with the situations they will encounter after graduation. Engineering students, for example, can learn how to communicate with clients, test a design and respond when a project does not go according to plan. These abilities are difficult to develop through lectures alone. Placements and supervised projects also help students make informed choices about their careers rather than relying on assumptions about a particular profession.

On the other hand, universities should provide more than immediate preparation for a specific job. A sound understanding of theory enables graduates to evaluate new information and adapt when technology changes. Without mathematical principles, an engineer may know how to operate a familiar tool but struggle to assess whether a new design is reliable. Academic study can also encourage students to question ideas, compare evidence and explain their conclusions clearly.

For these reasons, university courses should combine rigorous teaching with opportunities to apply knowledge. A student might first study the principles behind an environmental problem, then work with a local organisation to investigate a practical solution. Teachers could assess both the quality of the research and the decisions made during the project.

In conclusion, neither practical training nor academic learning is sufficient on its own. Universities serve students best when they connect strong theoretical foundations with meaningful experience.`;

export function TourStage(){
 const tour=useTour(),teacher=tour.activeRoleTour==='teacher',index=tour.currentStepIndex;
 const [code,setCode]=useState(''),[joined,setJoined]=useState(false),[message,setMessage]=useState(''),[drillAnswer,setDrillAnswer]=useState('');
 const typing=useRef<ReturnType<typeof setInterval>|null>(null);
 const stopTyping=()=>{if(typing.current){clearInterval(typing.current);typing.current=null;}};
 const [draft,setDraft]=useState(()=>({...normalizeDraft(null),userId:'tour-sample',prompt:'Some people believe universities should focus on practical skills. Others value academic knowledge. Discuss both views and give your opinion.',essay:sampleEssay,started:null,mode:'check'}));
 useEffect(()=>{
  setMessage('');stopTyping();
  if(!teacher&&index===1){
   setCode('');setJoined(false);let i=0;
   typing.current=setInterval(()=>{i++;setCode('FOG1XXXX'.slice(0,i));if(i===8)stopTyping();},140);
  }
  if(!teacher&&index===4){setDrillAnswer('');setDraft(d=>({...d,started:Date.now(),mode:'practice'}));}
  return stopTyping;
 },[teacher,index]);
 const noop=()=>{},sampleAction=()=>setMessage('Thao tác minh họa hoàn tất. Dữ liệu thật không thay đổi.');
 let page;
 if(!teacher&&index===0)page=<Overview draft={normalizeDraft(null)} currentUserId="tour-sample" count={0} go={noop} preview={noop}/>;
 else if((!teacher&&index===1)||(teacher&&index<3))page=<><div className="page-heading"><div><h1>My Classes</h1><p>Fog1 · Lớp minh họa của thầy Nguyên</p></div></div>
  {teacher?<><div className="surface classroom-form" data-tour="teacher-create-class"><label htmlFor="tour-class-name">Create a class<input id="tour-class-name" name="tourClass" defaultValue="Writing Task 2 — Fog1"/></label><button className="primary" onClick={sampleAction}>Create Class</button></div><div className="surface tour-invite" data-tour="teacher-invite-controls" data-tour-preview="click" onClick={sampleAction}><strong>Fog1</strong><code>FOG1XXXX</code><button className="secondary" onClick={sampleAction}>Copy</button><button className="text-button" onClick={sampleAction}>Copy invite link</button><button className="text-button" onClick={sampleAction}>Regenerate code</button></div>
  {index>=1&&<section className="surface class-detail" data-tour="teacher-class-roster"><h2>Class members</h2><label htmlFor="tour-roster-search">Search class members<input id="tour-roster-search" name="tourRoster" placeholder="Search name or email"/></label>{[['Minh Anh','minhanh@example.test','2'],['Hoàng Nam','nam@example.test','1']].map(([name,email,count])=><div className="member-row" key={email}><span><strong>{name}</strong><small className="member-email">{email}</small><small>{count} submissions · Student</small></span><button className="secondary" onClick={sampleAction}>Remove student</button></div>)}</section>}
  {index===2&&<section className="surface class-detail" data-tour="teacher-class-submissions"><h2>Class writing</h2><details open><summary>Minh Anh · DEMO0001 · COMPLETED · Band 6.5</summary><p className="essay-text">{draft.essay}</p><div className="tour-override" data-tour="teacher-score-override">{['TR','CC','LR','GRA'].map(key=><label key={key} htmlFor={'tour-override-'+key}>{key}<input id={'tour-override-'+key} name={'tour'+key} type="number" min="0" max="9" step="0.5" defaultValue={key==='LR'?'6.0':key==='GRA'?'7.0':'6.5'}/></label>)}<label htmlFor="tour-review-reason">Reason for review<input id="tour-review-reason" name="tourReason" placeholder="Nhận xét của giáo viên"/></label><button className="primary" onClick={sampleAction}>Save reviewed scores</button></div></details></section>}</>:
  <div className="surface classroom-form"><label htmlFor="tour-invite">Teacher invite code<input id="tour-invite" name="tourInvite" data-tour="join-class-input" value={code} onFocus={stopTyping} onPointerDown={stopTyping} onChange={e=>{stopTyping();setCode(e.target.value);}}/></label><button className="primary" data-tour="tour-join-submit" data-tour-preview="click" onClick={()=>setJoined(true)}>Join Class</button>{joined&&<p role="status">Fog1 · Active · 3/3 credits (minh họa)</p>}</div>}
 </>;
 else if(!teacher&&index===3)page=<TourSampleFeedbackModal/>;
 else if(!teacher&&index===5)page=<section className="surface tour-journal" data-tour="writing-journal"><h1>Your writing journal.</h1><p>Mở bài để xem lại band, nhận xét và bài tập cá nhân hóa.</p><button className="history-list" onClick={sampleAction}>DEMO0001 · Universities and practical skills <strong>Overall 6.5 →</strong></button><button className="history-list" onClick={sampleAction}>DEMO0002 · FAILED<strong>Mở nội dung đã lưu → Edit &amp; Resubmit</strong></button><p>Nháp chưa nộp? Mở Overview → Continue draft.</p><span className="tour-sandbox-label">Dữ liệu minh họa · Replay ở góc dưới bên phải</span></section>;
 else page=<div data-tour={!teacher&&index===4?'practice-workspace':undefined}><EssayEditor draft={{...draft,started:!teacher&&index===4?draft.started:null}} setDraft={setDraft} timed={!teacher&&index===4} busy={false} elapsed={0} error="" onSubmit={sampleAction} experiment="V1_STRATIFIED" setExperiment={noop} storageError={false} onEdit={noop} go={noop} draftUserId="tour-sample" demoClassName="Fog1 · Lớp minh họa"/>{!teacher&&index===4&&<aside className="surface tour-drill-preview"><h2>Skill Practice · Sau khi chấm</h2><p>Chọn dạng đúng: Many students ___ practical experience.</p><button className="secondary" data-tour="sample-drill-answer" data-tour-preview="click" onClick={()=>setDrillAnswer('need')}>need</button> <button className="secondary" onClick={()=>setDrillAnswer('needs')}>needs</button>{drillAnswer&&<p role="status" data-tour="sample-drill-feedback">{drillAnswer==='need'?'Đúng · “Many students” đi với “need”.':'Thử lại: “students” là chủ ngữ số nhiều.'}</p>}<p>Trả lời đủ bộ → Submit all responses. Phần này minh họa bài tập, độc lập với đồng hồ viết bài ở trên.</p></aside>}</div>;
 return <div data-tour-sandbox><Shell route={teacher?(index<3?'classes':'check'):index===0?'overview':index===1?'classes':index===2?'check':index===3?'feedback':index===4?'write':'history'} busy={true} go={noop}><div className="tour-sandbox-banner"><span>Minh họa tương tác · {teacher?'Giáo viên':'Học sinh'} · Không gọi AI, không lưu bài thật</span><strong data-tour="credits-badge">{teacher?'20/20':joined||index>=2?'3/3':'0/3'} credits today · Mẫu</strong></div>{message&&<p className="notice" role="status">{message}</p>}{page}</Shell></div>;
}
