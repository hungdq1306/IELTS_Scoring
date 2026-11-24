import {useState} from 'react';
import {samplePassage} from './sample-data';
export function TourSampleFeedbackModal(){
 const [open,setOpen]=useState(false);
 return <section className="surface tour-sample" aria-label="Assessment mẫu">
  <span className="tour-sandbox-label">Bài mẫu minh họa — Không tốn credit</span><h1>Your writing, clearer.</h1>
  <div data-tour="sample-band-scores" className="tour-bands"><strong>Overall <b>6.5</b></strong>{[['TR','6.5'],['CC','6.5'],['LR','6.0'],['GRA','7.0']].map(([label,value])=><span key={label}>{label}<b>{value}</b></span>)}</div>
  <h2>Essay & sentence feedback</h2><p>Trích đoạn từ bài mẫu gốc ở bước trước.</p><p className="tour-essay">{samplePassage.before}<button className="tour-error" data-tour="sample-error-highlight" data-tour-preview="click" aria-expanded={open} onClick={()=>setOpen(v=>!v)}>{samplePassage.quote}</button>{samplePassage.after}</p>
  <span className="tour-mint">A clear position supported by relevant ideas.</span>
  {open&&<aside data-tour="sample-correction-card" className="tour-correction" aria-live="polite"><strong>Gợi ý theo phong cách thầy Nguyên · minh họa</strong><p>“Students” là chủ ngữ số nhiều; dùng “have”. Giữ ý gốc, sửa đúng lỗi trước khi nâng cấp cách diễn đạt.</p><div><b>Minimal Fix</b><p>Many students <em>have</em> difficulty finding practical opportunities.</p></div><div><b>Band Upgrade</b><p>Many students struggle to gain practical experience alongside their academic studies.</p></div><small>Gợi ý mẫu do ứng dụng minh họa; không phải nhận xét thật của giáo viên hay cam kết tăng band.</small></aside>}
 </section>;
}
