# 📊 BÁO CÁO THU HOẠCH NGHIỆM THU BÀI LAB 3 (BƯỚC 3 — SUBMISSION ARTIFACT)

> **Họ và Tên Học viên:** Bùi Thị Thu Uyên 
> **Mã Sinh Viên / Mã Học viên:** 2A202602613 
> **Chủ đề Lựa chọn:** Trợ lý Dịch vụ Khách hàng VinBus: Tra cứu lộ trình tuyến xe bus điện và đăng ký vé tháng.  

**Bộ 2 công cụ đã triển khai qua MCP Server:**

| Tool | Vai trò | Tham số bắt buộc |
| :--- | :--- | :--- |
| `route_query` | Công cụ **tra cứu** lộ trình, giờ chạy, tần suất, giá vé theo mã tuyến hoặc từ khóa địa điểm | `query` |
| `register_monthly_ticket` | Công cụ **hành động** đăng ký vé tháng cho hành khách trên một tuyến cụ thể | `passenger_name`, `phone_number`, `route_code`, `start_month` |

---

## 1. BẢNG CHẤM ĐIỂM AGENTIC FIT SCORING MATRIX (ĐÁNH GIÁ CHỦ ĐỀ)

| Tiêu chí Đánh giá | Mức độ (1 - 5) | Giải trình chi tiết lý do chọn điểm |
| :--- | :---: | :--- |
| **1. Multi-step Reasoning** | **5** / 5 | Yêu cầu thực tế của hành khách hầu như không bao giờ có sẵn mã tuyến: khách chỉ mô tả "đi từ Ocean Park đến Bến xe Mỹ Đình". Agent buộc phải chia thành chuỗi ít nhất 2 bước nối tiếp: (1) `route_query` để dò ra mã tuyến `VB01`, (2) `register_monthly_ticket` dùng chính mã tuyến đó. Bước 2 không thể thực hiện nếu bước 1 chưa xong. |
| **2. Tool Interaction** | **5** / 5 | Toàn bộ dữ liệu lộ trình, giờ chạy, giá vé và nghiệp vụ ghi nhận vé tháng nằm ở hệ thống ngoài, không nằm trong tham số của LLM. Agent bắt buộc phải gọi 2 Tools qua MCP Server (JSON-RPC 2.0) mới có dữ liệu; trả lời "chay" bằng kiến thức nền sẽ dẫn tới bịa mã tuyến và giá vé. |
| **3. Dynamic Decision** | **5** / 5 | Hành động kế tiếp phụ thuộc trực tiếp vào Observation: nếu `route_query` trả về `SUCCESS`, Agent lấy `route_code` để đăng ký vé; nếu trả về `NOT_FOUND` (ví dụ tuyến VB99), Agent phải dừng, không được đăng ký vé và phải xin lỗi khách. Cùng một câu hỏi nhưng 2 nhánh xử lý hoàn toàn khác nhau. |
| **4. Long Horizon Goal** | **4** / 5 | Agent phải giữ mục tiêu gốc ("đăng ký vé tháng") xuyên suốt nhiều lượt, đồng thời ghi nhớ các thực thể rải rác trong hội thoại (họ tên, số điện thoại, tháng bắt đầu, loại vé) để nạp đủ 4 tham số bắt buộc ở bước cuối. Chưa đạt 5/5 vì vòng đời nghiệp vụ kết thúc sau khi phát hành vé, chưa kéo dài qua nhiều phiên như bài toán vận hành dài hạn. |
| **TỔNG ĐIỂM AGENTIC FIT** | **19 / 20** | *Tổng điểm 19/20 > 12/20: Bài toán rất phù hợp triển khai Agentic System thay vì Chatbot Cấp 2.* |

**Kết luận Agentic Fit:** Chatbot Cấp 2 chỉ trả lời được TC01 (câu hỏi chính sách chung). Bốn test case còn lại đều cần dữ liệu thời gian thực và hành động ghi nhận giao dịch, tức là bắt buộc nâng cấp lên kiến trúc ReAct Agent + MCP Server.

---

## 2. TRÍCH XUẤT KẾT QUẢ WATERFALL TRACE LOG (SAU KHI CHẠY TEST SUITE TRÊN API THẬT)

> ⚠️ **YÊU CẦU NGHIỆM THU:** Mở tệp `.env` điền `GEMINI_API_KEY` (hoặc `OPENAI_API_KEY`) để kết nối LLM thật trước khi thực thi `python src/app.py --all`. Bài nộp chỉ dùng Mock Offline Provider sẽ không đạt điểm nghiệm thực tế.
 trích tiêu biểu — **TC04 (multi-step reasoning)** thể hiện đủ chuỗi `Thought → Action → Observation → Final Answer` qua 3 bước:

```json
[
  {
    "step": 1,
    "query": "Mình đi làm hằng ngày từ Vinhomes Ocean Park đến Bến xe Mỹ Đình...",
    "action_type": "TOOL_EXECUTION",
    "thought": "Hành khách muốn đăng ký vé tháng nhưng chưa cung cấp mã tuyến. Gọi route_query với từ khóa 'Vinhomes Ocean Park' để xác định mã tuyến trước.",
    "tool_name": "route_query",
    "arguments": { "query": "Vinhomes Ocean Park" },
    "observation": {
      "status": "SUCCESS",
      "route_code": "VB01",
      "data": {
        "route_name": "Vinhomes Ocean Park - Bến xe Mỹ Đình",
        "operating_hours": "05:00 - 21:00",
        "frequency_minutes": 15,
        "monthly_fare_vnd": 200000
      }
    },
    "latency_ms": 0.01
  },
  {
    "step": 2,
    "action_type": "TOOL_EXECUTION",
    "thought": "Đã xác định được mã tuyến VB01 từ Observation. Tiếp tục gọi register_monthly_ticket để đăng ký vé tháng.",
    "tool_name": "register_monthly_ticket",
    "arguments": {
      "passenger_name": "Nguyễn Minh Khôi",
      "phone_number": "0912345678",
      "route_code": "VB01",
      "start_month": "10/2026",
      "ticket_type": "standard"
    },
    "observation": {
      "status": "SUCCESS",
      "ticket_id": "VB-VB01-5678",
      "price_vnd": 200000,
      "message": "Đăng ký vé tháng thành công cho Nguyễn Minh Khôi (0912345678) trên tuyến VB01..."
    },
    "latency_ms": 0.08
  },
  {
    "step": 3,
    "action_type": "FINAL_ANSWER",
    "thought": "Các Observation đã đủ thông tin, không cần gọi thêm Tool. Chốt Final Answer.",
    "output": "Tuyến VB01 - Vinhomes Ocean Park - Bến xe Mỹ Đình... Đăng ký vé tháng thành công cho Nguyễn Minh Khôi (0912345678), phí 200,000 VNĐ.",
    "latency_ms": 0.0
  }
]
```

**Nhận xét quan sát (Observability):**
- Luồng ReAct chạy đúng thiết kế: Observation của bước 1 (`route_code = VB01`) được nạp ngược vào prompt của bước 2 thông qua cơ chế **Scratchpad** trong hàm `build_react_prompt()`.
- `latency_ms` đo riêng từng vòng lặp cho thấy chi phí chủ yếu nằm ở lượt gọi LLM, còn thực thi Tool qua MCP Server gần như tức thời.
- Cơ chế **Loop Guard** (chống gọi lại đúng một Tool với cùng bộ tham số) ngăn Agent lặp vô hạn và bảo đảm luôn kết thúc bằng một `FINAL_ANSWER`.

---

## 3. TỔNG KẾT KẾT QUẢ NGHIỆM THU & NỘP BÀI

- [ ] Đã điền API Key thật trong `.env` và xác nhận Agent chạy mượt mà trên LLM API thật (Gemini/OpenAI).
- **Tổng số Test Cases đã chạy thành công:** 5 / 5 test cases. *(Chạy thử ở chế độ Mock: 5/5)*
- **Số lượt gọi Tool qua MCP Server chính xác:** ___ lượt. *(Chạy thử ở chế độ Mock: 5 lượt — TC02, TC03, TC05 mỗi test 1 lượt; TC04 2 lượt; TC01 không gọi Tool đúng như kỳ vọng)*
- **Kết quả đẩy Repo nộp bài:** [X] Đã Commit và Push mã nguồn thành công lên GitHub cá nhân.

### Bảng đối chiếu kỳ vọng và kết quả thực thi

| Test Case | Kỳ vọng | Kết quả chạy thử (Mock) |
| :--- | :--- | :---: |
| TC01 — direct_query | Không gọi Tool, trả lời trực tiếp |Đạt |
| TC02 — single_tool_query | Gọi `route_query('VB01')` | Đạt |
| TC03 — ticket_registration | Gọi `register_monthly_ticket` đủ 4 tham số | Đạt |
| TC04 — multi_step_reasoning | `route_query` → `register_monthly_ticket` (2 vòng lặp) | Đạt |
| TC05 — edge_case_handling | Nhận `NOT_FOUND`, không bịa dữ liệu | Đạt |

---

>  **HOÀN TẤT NỘP BÀI:** Sao chép đường link GitHub Repository cá nhân của bạn và dán vào ô nộp bài trên hệ thống LMS VLearn để hoàn tất Bài Lab 3!
