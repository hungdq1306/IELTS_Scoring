export type TourRole = 'student' | 'teacher';
export type TourStep = {route:string; target:string; title:string; body:string};
export const tours:Record<TourRole,TourStep[]> = {
 student:[
  {route:'/overview',target:'credits-badge',title:'Biết số lượt chấm của bạn',body:'Chưa vào lớp: 0 lượt. Vào lớp: mặc định 3 lượt/ngày, tùy cấu hình lớp. Lượt làm mới lúc 00:00 Việt Nam; bài chấm FAILED được hoàn lượt.'},
  {route:'/classes',target:'join-class-input',title:'Nhập mã giáo viên, chọn đúng lớp',body:'Con trỏ đang nhập mã mẫu FOG1XXXX. Trong lớp thật, dùng mã giáo viên gửi rồi Join Class; kiểm tra lớp đang chọn trước khi nộp.'},
  {route:'/check',target:'essay-workspace',title:'Đưa đề và bài viết vào đây',body:'Kiểm tra lớp nhận bài, dán đầy đủ đề và bài, hướng tới ít nhất 250 từ. Submit essay mở xác nhận trước khi gửi chấm.'},
  {route:'/assessment',target:'sample-band-scores',title:'Xem band rồi mở sửa câu',body:'Xem bốn tiêu chí, sau đó theo con trỏ đến câu tô màu. Minimal Fix sửa lỗi trực tiếp; Band Upgrade minh họa cách diễn đạt tốt hơn.'},
  {route:'/practice',target:'practice-workspace',title:'Viết có giờ, rồi luyện điểm yếu',body:'Writing Practice là viết đề trong 40 phút; nháp tự lưu theo tài khoản. Bài tập cá nhân hóa nằm ở Skill Practice sau assessment: trả lời đủ bộ rồi Submit all responses.'},
  {route:'/history',target:'writing-journal',title:'Trở lại bài cũ và tiếp tục tiến bộ',body:'History giữ cả bài hoàn tất và bài FAILED. Mở bài lỗi để đọc lại nội dung rồi Edit & Resubmit; bài hoàn tất mở band, nhận xét và bài tập. Continue draft ở Overview dành cho nháp. Nút Hướng dẫn sử dụng mở lại tour bất kỳ lúc nào.'},
 ],
 teacher:[
  {route:'/classes',target:'teacher-create-class',title:'Tạo lớp và chia sẻ lời mời',body:'Create Class tạo lớp. Theo con trỏ tới mã mời: Copy code/link để gửi học sinh; Regenerate code làm mã cũ hết hiệu lực. Mọi thao tác ở đây là minh họa.'},
  {route:'/classes',target:'teacher-class-roster',title:'Nhìn rõ học sinh trong lớp',body:'View class mở tên, email và số bài của từng học sinh. Tìm nhanh bằng ô tìm kiếm; kiểm tra đúng người ở hộp xác nhận trước khi xóa khỏi lớp.'},
  {route:'/classes',target:'teacher-class-submissions',title:'Xem bài và đánh giá lại điểm',body:'Mở Class writing để đọc bài và band. Giáo viên chủ lớp/admin có thể sửa điểm với lý do; TA chỉ đọc lớp được phân công.'},
  {route:'/check',target:'credits-badge',title:'Dùng lượt chấm của giáo viên',body:'Giáo viên mặc định có 20 lượt/ngày để thử đề và bài; admin có thể đổi quota. Bản tour không tạo lớp, gửi bài hoặc trừ bất kỳ lượt nào.'},
 ],
};
