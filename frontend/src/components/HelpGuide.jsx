import {useState} from 'react';
import {ArrowRight, BookOpen, Clock3, FileCheck2, GraduationCap, Shield, Users} from 'lucide-react';
import {useAuth} from '../auth-context';
import './help-guide.css';

const studentSteps = [
 ['Tham gia lớp học', 'Đăng nhập bằng Sign in, đọc và chấp nhận điều kiện tham gia. Mở My Classes, nhập mã giáo viên gửi vào Teacher invite code rồi chọn Join Class. Nếu có nhiều lớp, chọn Use for my next essay ở đúng lớp trước khi nộp.', 'classes', 'Mở My Classes'],
 ['Chọn cách viết phù hợp', 'Writing Practice: chọn đề trong thư viện, Surprise me để lấy đề ngẫu nhiên hoặc Use my own prompt để nhập đề riêng. Nhấn Start writing để bắt đầu 40 phút. Check My Essay: dán đầy đủ đề Task 2 và bài đã viết, không có đồng hồ đếm ngược.', 'topics', 'Chọn đề luyện viết'],
 ['Nộp bài một lần', 'Kiểm tra Submitting to để biết lớp nhận bài. Nhấn Submit essay, đọc hộp xác nhận rồi chọn Assess my essay. Theo dõi trạng thái xử lý; tránh nhấn nộp liên tục. Mục tiêu Task 2 là ít nhất 250 từ; hệ thống có thể nhận bài ngắn hơn nhưng sẽ cảnh báo.', 'check', 'Mở Check My Essay'],
 ['Đọc nhận xét theo từng tiêu chí', 'Xem Overall rồi lần lượt TR, CC, LR và GRA. Chọn tiêu chí để lọc nhận xét; nhấn phần được đánh dấu trong bài để đọc giải thích và gợi ý sửa. Ưu tiên 1–2 điểm cần cải thiện thay vì chỉ nhìn band.', null, null],
 ['Luyện từ chính bài của bạn', 'Từ assessment, chọn phần luyện tập hoặc Skill Practice. Nhấn Generate Practice Exercises nếu chưa có bộ bài. Điền đủ câu trả lời, dùng Previous exercise / Next exercise để chuyển câu, Save responses để lưu, rồi Submit all responses để nhận nhận xét cho cả bộ.', 'skills', 'Mở Skill Practice'],
 ['Sửa bài và xem lại tiến bộ', 'Trong Revision & progress, xem kết quả, số lần dùng gợi ý và các kỹ năng đã luyện. Chọn đoạn ở Original paragraph, nhập bản sửa rồi Check revision. Dùng History để mở lại bài và nhận xét; Continue draft ở Overview để tiếp tục bài nháp.', 'history', 'Mở History'],
];
const staffSteps = [
 ['Tạo lớp và gửi lời mời', 'Giáo viên/admin mở My Classes → Create a class → Create Class. Dùng Copy hoặc Copy invite link để gửi mã/liên kết. Regenerate code thay mã cũ; liên kết cũ sẽ hết hiệu lực. TA không có quyền tạo hay quản lý lớp.', 'classes', 'Mở My Classes'],
 ['Quản lý lớp và danh sách học sinh', 'Chỉnh tên, Daily student credits hoặc Class active rồi Save class settings. View class hiển thị tên, email, ngày tham gia và số bài; Search class members giúp tìm nhanh. Remove student yêu cầu xác nhận đúng người. Assign TA cần tài khoản đã được cấp vai trò phù hợp.', 'classes', 'Xem lớp học'],
 ['Đọc bài và phản hồi điểm', 'Trong View class → Class writing, mở bài để xem học sinh, mã bài, thời gian, nội dung và band. Chủ lớp/admin có thể sửa điểm bốn tiêu chí, nhập Reason for review và Save reviewed scores. TA chỉ đọc các lớp được phân công.', null, null],
];
const adminSteps = [
 ['Tài khoản và quyền truy cập', 'Mở Administration → Accounts. Tìm theo tên/email, lọc vai trò, trạng thái hoặc lớp; dùng Previous page / Next page nếu cần. Thay role, trạng thái hoặc bonus credits, chọn Save account và kiểm tra người nhận cùng các thay đổi trước khi xác nhận. Không thể tự hạ quyền hoặc khóa tài khoản admin đang dùng.', 'admin', 'Mở Administration'],
 ['Theo dõi vận hành và xử lý lỗi', 'Usage overview hiển thị bài hôm nay, job lỗi, hàng đợi, độ trễ và token/chi phí. Grading jobs cho phép tìm và lọc job. Chỉ retry bài chấm bị FAILED khi đã kiểm tra nguyên nhân; nhập lý do trước khi Retry failed assessment. Audit logs giúp truy vết thay đổi.', null, null],
 ['Đổi cấu hình có kiểm soát', 'Trong System settings, thay quota, phiên bản chấm hoặc calibration rồi Save settings. Mặc định quota học sinh mới chỉ áp dụng cho lớp tạo sau đó. Chỉ chọn Also overwrite quota… khi chủ đích đổi toàn bộ lớp đang hoạt động và kiểm tra hộp xác nhận. Chưa cấu hình giá thì chi phí không có nghĩa là $0.', null, null],
];
const faqs = [
 ['Không nộp được bài?', 'Đảm bảo đã đăng nhập, chấp nhận điều kiện, tham gia lớp đang hoạt động và chọn lớp nếu có nhiều lớp. Đề phải đủ nội dung, bài không được trống. Kiểm tra credits còn lại và thông báo dưới nút Submit essay.'],
 ['Credits được tính như thế nào?', 'Bản lớp học hiển thị số lượt còn lại trong menu tài khoản. Lượt chấm làm mới lúc 00:00 giờ Việt Nam (UTC+7). Bài chấm lỗi vĩnh viễn được hoàn lượt; lỗi tạo bài tập sau một lần chấm thành công không hoàn lượt chấm đó. Quota có thể khác theo lớp và vai trò.'],
 ['Bài nháp có tự lưu không?', 'Bài nháp được lưu trong trình duyệt theo tài khoản. Continue draft ở Overview khôi phục chế độ và đồng hồ của bài luyện. Đồng hồ tính theo thời gian đã trôi qua, kể cả khi bạn rời trang. Xóa dữ liệu trình duyệt hoặc đổi thiết bị có thể làm mất nháp; kiểm tra cảnh báo Draft not saved và sao chép bài nếu cần.'],
 ['Hết 40 phút thì sao?', 'Bạn có thể nộp bài hoặc chọn continue with extra time để viết tiếp; thời gian thêm được ghi nhận. Chuyển sang Check My Essay sẽ kết thúc phiên luyện có giờ sau khi bạn xác nhận.'],
 ['Đang chờ chấm thì mất mạng hoặc đóng trang?', 'Trong bản lớp học, job đã được nhận sẽ tiếp tục được xử lý. Khi kết nối lại, mở History và chọn bài để xem trạng thái/nhận xét. Không tạo nhiều yêu cầu nộp mới cho cùng một bài. Nếu báo lỗi, giữ bản sao nội dung và liên hệ giáo viên.'],
 ['Vì sao Skill Practice chưa có bài tập?', 'Cần có assessment của chính bạn trước. Mở bài từ History rồi vào Skill Practice và chọn Generate Practice Exercises. Bài mẫu chỉ minh họa. Nếu AI không tìm được bài tập đủ căn cứ, trang có thể không có câu hỏi; hãy dựa vào nhận xét hoặc trao đổi với giáo viên.'],
 ['Band này có phải kết quả IELTS chính thức?', 'Không. Đây là ước lượng phục vụ luyện tập. TR: đáp ứng đề; CC: mạch lạc và liên kết; LR: vốn từ; GRA: độ đa dạng và chính xác ngữ pháp. Nhận xét AI có thể sai; dùng bằng chứng trong bài và ý kiến giáo viên để kiểm tra.'],
 ['Tôi tìm hồ sơ, đăng xuất hoặc đổi lớp ở đâu?', 'Mở menu tài khoản ở cuối thanh bên: My Profile xem hồ sơ; Account Settings mở cài đặt tài khoản; My Classes tham gia/chọn lớp; Sign Out đăng xuất. Trên điện thoại, mở nút Open navigation trước. Không đưa thông tin cá nhân nhạy cảm vào bài gửi AI.'],
];

export function HelpGuide({go, preview}) {
 const auth=useAuth();
 const [audience,setAudience]=useState(()=>['admin','teacher','ta'].includes(auth.account?.role)?auth.account.role==='admin'?'admin':'staff':'student');
 const [query,setQuery]=useState('');
 const [error,setError]=useState('');
 const demo=auth.status==='demo', visitor=auth.status==='visitor';
 const steps=audience==='student'?studentSteps:audience==='staff'?staffSteps:adminSteps;
 const matches=faqs.filter(row=>row.join(' ').toLocaleLowerCase('vi').includes(query.trim().toLocaleLowerCase('vi')));
 const act=async route=>{setError('');try{if(visitor)await auth.signIn();else go(route);}catch(e){setError(e.message||'Không mở được đăng nhập. Vui lòng thử lại.');}};
 return <div className="help-guide" lang="vi">
  <header className="guide-hero"><div><span className="eyebrow">FOGWRITE · BẮT ĐẦU TẠI ĐÂY</span><h1>Hướng dẫn sử dụng</h1><p>Từ bài viết đầu tiên đến buổi luyện tập tiếp theo. Làm theo từng bước, với tên nút giống hệt trên web.</p><div className="actions"><button className="primary" onClick={preview}>Xem bài mẫu <ArrowRight size={17}/></button><a className="guide-anchor" href="#guide-steps">Bắt đầu từng bước ↓</a></div></div><BookOpen size={56} aria-hidden="true"/></header>
  {demo&&<aside className="guide-demo" role="note"><strong>Bạn đang xem bản demo local.</strong> Bạn có thể thử đề, đồng hồ, nháp và bài mẫu mà không đăng nhập. My Classes, credits và Administration thuộc bản lớp học có đăng nhập. Chấm bài thật và tạo bài tập cần dịch vụ AI; bài mẫu không gọi AI.</aside>}
  {visitor&&<aside className="guide-demo">Bạn có thể đọc hướng dẫn và xem bài mẫu ngay. Các thao tác với bài của bạn cần đăng nhập. Tài khoản mới bắt đầu với vai trò học sinh.</aside>}
  {error&&<p className="notice error" role="alert">{error}</p>}
  <section className="guide-choices" aria-label="Chọn cách bắt đầu"><article className="surface"><Clock3 size={23}/><h2>Muốn luyện như đi thi?</h2><p>Chọn đề, viết trong 40 phút, rồi xem nhận xét.</p><button className="text-button" onClick={()=>act('topics')}>Writing Practice <ArrowRight size={16}/></button></article><article className="surface"><FileCheck2 size={23}/><h2>Đã có bài viết?</h2><p>Dán đề và bài vào trình kiểm tra, không giới hạn giờ.</p><button className="text-button" onClick={()=>act('check')}>Check My Essay <ArrowRight size={16}/></button></article></section>
  <section id="guide-steps" className="guide-section"><h2>Lộ trình theo vai trò</h2><p>Các mục bên dưới giải thích tính năng; quyền sử dụng phụ thuộc tài khoản được cấp.</p><div className="guide-tabs" role="group" aria-label="Vai trò trong hướng dẫn">{[['student','Học sinh',GraduationCap],['staff','Giáo viên / TA',Users],['admin','Quản trị viên',Shield]].map(([key,label,Icon])=><button key={key} className={audience===key?'primary':'secondary'} aria-pressed={audience===key} onClick={()=>setAudience(key)}><Icon size={17}/>{label}</button>)}</div><ol className="guide-steps">{steps.map(([title,body,route,label],i)=><li key={title} className="surface"><span className="guide-number" aria-hidden="true">{i+1}</span><div><h3>{title}</h3><p>{body}</p>{route&&!(demo&&['classes','admin'].includes(route))&&(!['classes','admin'].includes(route)||audience==='student'||auth.account?.role==='admin'||audience==='staff'&&['teacher','ta'].includes(auth.account?.role))&&<button className="text-button" onClick={()=>act(route)}>{label}<ArrowRight size={16}/></button>}</div></li>)}</ol></section>
  <section className="guide-section surface guide-faq"><h2>Gỡ vướng nhanh</h2><label htmlFor="guide-search">Tìm câu hỏi<input id="guide-search" name="guideSearch" type="search" placeholder="Ví dụ: credits, bài nháp, mất mạng…" value={query} onChange={e=>setQuery(e.target.value)}/></label><p className="guide-match-count" role="status">{matches.length} câu hỏi phù hợp</p>{matches.map(([q,a])=><details key={q}><summary>{q}</summary><p>{a}</p></details>)}{!matches.length&&<p>Chưa có câu hỏi phù hợp. Thử từ khóa khác hoặc hỏi giáo viên kèm thông báo lỗi bạn gặp.</p>}</section>
  <footer className="guide-footer"><p>Thử một vòng: xem bài mẫu → chọn đề → viết nháp → quay lại Overview → Continue draft.</p><button className="primary" onClick={()=>act('overview')}>Về studio <ArrowRight size={17}/></button></footer>
 </div>;
}
