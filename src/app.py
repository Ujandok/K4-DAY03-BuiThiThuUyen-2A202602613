"""
🚀 CORE AGENT APPLICATION (DAY 03: CHATBOT VS REACT AGENT)
Thực thi so sánh giữa Chatbot Baseline (Cấp 2) và ReAct Agent kết nối MCP Server (Cấp 3).
"""
import json
import os
import sys
import time
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from mcp_server import MCPVinBusServer
from prompts import (
    CHATBOT_BASELINE_PROMPT,
    REACT_AGENT_SYSTEM_PROMPT,
    MAX_ITERATIONS
)
from providers import get_llm_provider

load_dotenv()

def load_test_cases():
    """Tải danh sách 5 test cases từ config/test_cases.json hoặc config/test_cases.example.json"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config", "test_cases.json")
    if not os.path.exists(config_path):
        example_path = os.path.join(base_dir, "config", "test_cases.example.json")
        if os.path.exists(example_path):
            print("⚠️ [CONFIG NOTICE]: Chưa thấy file 'config/test_cases.json'. Đang dùng mẫu 'config/test_cases.example.json'.")
            print("👉 Hãy chạy: copy config/test_cases.example.json config/test_cases.json và viết test cases theo đề tài của bạn!\n")
            config_path = example_path
        else:
            config_path = "test_cases.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_waterfall_trace(trace_data: list):
    """Ghi vết log Waterfall Trace Log ra file docs/trace_waterfall.json"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs_dir = os.path.join(base_dir, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    trace_path = os.path.join(docs_dir, "trace_waterfall.json")
    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(trace_data, f, ensure_ascii=False, indent=2)
    print(f"📊 [OBSERVABILITY]: Đã lưu {len(trace_data)} sự kiện Waterfall Trace tại '{trace_path}'!")


def run_baseline_chatbot(user_query: str, provider):
    """Chạy Chatbot gốc (Cấp 2) không có công cụ gọi Tool"""
    print(f"\n💬 [CHATBOT BASELINE] Câu hỏi: {user_query}")
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"🤖 Chatbot phản hồi:\n{response}")


def build_react_prompt(user_query: str, scratchpad: list) -> str:
    """
    Ghép câu hỏi gốc với lịch sử Action/Observation (Scratchpad) để nạp ngược
    kết quả quan sát cho lượt suy luận kế tiếp của LLM.
    """
    if not scratchpad:
        return user_query
    history = "\n".join(scratchpad)
    return (
        f"{user_query}\n\n"
        f"[LỊCH SỬ SUY LUẬN REACT ĐÃ THỰC HIỆN]\n{history}\n\n"
        f"[HƯỚNG DẪN BƯỚC TIẾP THEO]\n"
        f"- Nếu các Observation ở trên đã đủ dữ liệu: hãy trả lời cuối cùng bằng văn bản cho hành khách.\n"
        f"- Nếu vẫn còn thiếu dữ liệu: hãy gọi tiếp đúng Tool còn thiếu (không gọi lại Tool đã có kết quả).\n"
        f"- Chỉ dùng dữ liệu có trong Observation, không được bịa thêm thông tin."
    )


def summarize_observations(observations: list) -> str:
    """Tổng hợp Final Answer từ toàn bộ Observation đã thu thập được qua MCP Server."""
    if not observations:
        return "Chưa thu thập được dữ liệu nào từ MCP Server để trả lời."

    parts = []
    for obs in observations:
        status = obs.get("status")
        if status == "SUCCESS" and "data" in obs:
            d = obs["data"]
            parts.append(
                f"Tuyến {obs.get('route_code', '')} - {d.get('route_name', '')}: "
                f"chạy từ {d.get('origin', '')} đến {d.get('destination', '')}, "
                f"giờ hoạt động {d.get('operating_hours', '')}, tần suất {d.get('frequency_minutes', '')} phút/chuyến, "
                f"giá vé lượt {d.get('single_fare_vnd', '')} VNĐ, vé tháng {d.get('monthly_fare_vnd', '')} VNĐ "
                f"(các điểm dừng chính: {', '.join(d.get('main_stops', []))})."
            )
        elif status == "SUCCESS" and "message" in obs:
            parts.append(obs["message"])
        elif status == "NOT_FOUND":
            parts.append(obs.get("message", "Rất tiếc, hệ thống VinBus không tìm thấy thông tin quý khách yêu cầu."))
        else:
            parts.append(f"Phản hồi từ công cụ: {json.dumps(obs, ensure_ascii=False)}")
    return " ".join(parts)


def run_react_agent(user_query: str, provider, mcp_server: MCPVinBusServer) -> list:
    """
    [REACT AGENT LOOP] Thực thi vòng lặp Thought -> Action -> Observation với MCP Server.
    Kết quả Observation của mỗi bước được nạp ngược vào prompt cho bước kế tiếp,
    cho phép Agent suy luận nhiều bước liên tiếp (ví dụ: Tra cứu cố vấn -> Đặt lịch hẹn).
    Trả về danh sách trace log của phiên thực thi.
    """
    print(f"\n🤖 [REACT AGENT] Câu hỏi: {user_query}")

    step = 0
    trace_logs = []
    scratchpad = []          # Lịch sử Action/Observation nạp ngược cho LLM
    observations = []        # Toàn bộ dữ liệu quan sát được qua MCP Server
    executed_calls = set()   # Chống lặp vô hạn khi LLM gọi lại đúng 1 Tool + tham số
    has_final_answer = False
    tools_list = mcp_server.list_tools()

    while step < MAX_ITERATIONS:
        step += 1
        step_start_time = time.time()
        print(f"\n--- 🔄 Vòng lặp ReAct Loop (Step {step}/{MAX_ITERATIONS}) ---")

        # Gọi LLM với Native Tool Calling Specs (kèm lịch sử Observation của các bước trước)
        current_prompt = build_react_prompt(user_query, scratchpad)
        llm_response = provider.generate_with_tools(current_prompt, tools_list, system_prompt=REACT_AGENT_SYSTEM_PROMPT)
        latency_ms = round((time.time() - step_start_time) * 1000, 2)

        thought = llm_response.get("thought", "Đang suy luận...")
        print(f"🧠 [Thought]: {thought}")

        # ------------------------------------------------------------------
        # TRƯỜNG HỢP 1: LLM quyết định trả lời trực tiếp bằng văn bản -> kết thúc
        # ------------------------------------------------------------------
        if llm_response.get("type") == "text":
            final_content = llm_response.get("content", "") or summarize_observations(observations)
            print(f"🏁 [Final Answer]: {final_content}")
            trace_logs.append({
                "step": step,
                "query": user_query,
                "action_type": "FINAL_ANSWER",
                "thought": thought,
                "output": final_content,
                "latency_ms": latency_ms
            })
            has_final_answer = True
            break

        # ------------------------------------------------------------------
        # TRƯỜNG HỢP 2: LLM đề xuất gọi Tool (Action) -> thực thi qua MCP Server
        # ------------------------------------------------------------------
        elif llm_response.get("type") == "tool_call":
            tool_name = llm_response.get("tool_name")
            arguments = llm_response.get("arguments", {})
            print(f"🛠️ [Action Proposed]: {tool_name}({arguments})")

            # Chống lặp: nếu LLM gọi lại đúng Tool + tham số đã có kết quả thì dừng và tổng hợp
            signature = f"{tool_name}::{json.dumps(arguments, sort_keys=True, ensure_ascii=False)}"
            if signature in executed_calls:
                final_answer = summarize_observations(observations)
                print(f"♻️ [Loop Guard]: Tool '{tool_name}' đã được gọi với tham số này. Dừng vòng lặp và tổng hợp kết quả.")
                print(f"🏁 [Final Answer]: {final_answer}")
                trace_logs.append({
                    "step": step,
                    "query": user_query,
                    "action_type": "FINAL_ANSWER",
                    "thought": "Đã đủ dữ liệu Observation từ MCP Server, tổng hợp câu trả lời cuối cùng.",
                    "output": final_answer,
                    "latency_ms": latency_ms
                })
                has_final_answer = True
                break
            executed_calls.add(signature)

            # Thực thi Tool qua MCP Server (JSON-RPC 2.0)
            mcp_result = mcp_server.call_tool(tool_name, arguments)
            obs_data = mcp_result.get("result", {})

            if not obs_data:
                print("👁️ [Observation từ MCP Server]: {}")
                print("⚠️ [CHÚ Ý]: MCP Server trả về kết quả rỗng! Kiểm tra lại hàm call_tool() trong 'src/mcp_server.py'.")
            else:
                obs_str = json.dumps(obs_data, ensure_ascii=False)
                print(f"👁️ [Observation từ MCP Server]: {obs_str}")
                observations.append(obs_data)

            trace_logs.append({
                "step": step,
                "query": user_query,
                "action_type": "TOOL_EXECUTION",
                "thought": thought,
                "tool_name": tool_name,
                "arguments": arguments,
                "observation": obs_data,
                "latency_ms": latency_ms
            })

            # Nạp ngược Action + Observation vào Scratchpad cho lượt suy luận kế tiếp
            scratchpad.append(
                f"[Action {step}] {tool_name}({json.dumps(arguments, ensure_ascii=False)})\n"
                f"[Observation {step}] {json.dumps(obs_data, ensure_ascii=False)}"
            )
            continue

        # ------------------------------------------------------------------
        # TRƯỜNG HỢP 3: Phản hồi không hợp lệ -> dừng an toàn
        # ------------------------------------------------------------------
        else:
            print(f"⚠️ [Invalid Response]: Không nhận diện được kiểu phản hồi '{llm_response.get('type')}'. Dừng vòng lặp.")
            break

    # Nếu hết MAX_ITERATIONS mà LLM chưa chốt câu trả lời: tự tổng hợp từ Observation
    if not has_final_answer:
        final_answer = summarize_observations(observations)
        print(f"🏁 [Final Answer - Tổng hợp]: {final_answer}")
        trace_logs.append({
            "step": step + 1,
            "query": user_query,
            "action_type": "FINAL_ANSWER",
            "thought": f"Đã đạt giới hạn {MAX_ITERATIONS} vòng lặp hoặc LLM không chốt câu trả lời. Tổng hợp từ dữ liệu MCP Server.",
            "output": final_answer,
            "latency_ms": 0.0
        })

    return trace_logs


if __name__ == "__main__":
    print("==========================================================")
    print("🚌 VINBUS CUSTOMER AGENT - DAY 03 LAB: CHATBOT VS REACT AGENT")
    print("==========================================================")
    
    provider = get_llm_provider()
    mcp_server = MCPVinBusServer()
    
    print(f"🔌 LLM Provider: {provider.__class__.__name__}")
    print(f"🌐 MCP Server: {mcp_server.server_name}\n")
    
    tests = load_test_cases()
    print(f"✅ Đã tải thành công {len(tests)} Test Cases thử nghiệm.\n")
    
    if "--interactive" in sys.argv:
        print("🎮 [INTERACTIVE MODE] Trò chuyện trực tiếp với ReAct Agent:")
        print("💡 Gợi ý câu hỏi thử nghiệm:")
        print("   - Câu hỏi chung: 'VinBus có những hình thức thanh toán nào?'")
        print("   - Tra cứu lộ trình: 'Cho mình xem lộ trình và giờ chạy của tuyến VB01'")
        print("   - Đăng ký vé tháng: 'Đăng ký vé tháng tuyến E02 cho Trần Thị B, sđt 0987654321, từ tháng 10/2026'")
        print("   - Gõ 'exit' hoặc 'quit' để kết thúc phiên trò chuyện.\n")
        while True:
            try:
                user_input = input("👤 Sinh viên hỏi: ").strip()
                if not user_input or user_input.lower() in ["exit", "quit"]:
                    print("👋 Tạm biệt! Kết thúc phiên trò chuyện.")
                    break
                logs = run_react_agent(user_input, provider, mcp_server)
                save_waterfall_trace(logs)
            except (KeyboardInterrupt, EOFError):
                print("\n👋 Đã thoát phiên tương tác.")
                break
    elif "--all" in sys.argv:
        print("🚀 [TEST SUITE MODE] Kiểm tra 5 Test Cases:")
        completed_count = 0
        todo_count = 0
        all_traces = []
        
        for tc in tests:
            print(f"\n==================================================")
            print(f"🧪 [{tc['id']}] Loại test: {tc['type']} (Độ phức tạp: {tc['complexity']})")
            print(f"📌 Kỳ vọng: {tc['expected_behavior']}")
            
            if tc["question"].strip().startswith("TODO"):
                print(f"⏸️ [CHƯA KÍCH HOẠT - ĐANG LÀ TODO]:")
                print(f"   {tc['question']}")
                print(f"   👉 Hãy mở file 'config/test_cases.json' để viết câu hỏi thực tế cho Test Case này!")
                todo_count += 1
            else:
                logs = run_react_agent(tc["question"], provider, mcp_server)
                all_traces.extend(logs)
                completed_count += 1
                
        print(f"\n==================================================")
        print(f"📊 [KẾT QUẢ TEST SUITE]: Đã thực thi {completed_count}/{len(tests)} Test Cases | {todo_count} Test Cases đang chờ điền câu hỏi (TODO)")
        if all_traces:
            save_waterfall_trace(all_traces)
        print(f"💡 Để trò chuyện trực tiếp từng câu: Chạy 'python src/app.py --interactive'")
    else:
        # Chế độ mặc định khi chỉ gõ 'python src/app.py'
        print("ℹ️ HƯỚNG DẪN SỬ DỤNG CHƯƠNG TRÌNH:")
        print("  1. Chat trực tiếp liên tục:   python src/app.py --interactive")
        print("  2. Chạy toàn bộ Test Cases:    python src/app.py --all\n")
        
        sample_query = tests[1]["question"]
        print(f"--- 🏁 DEMO CHẠY THỬ 1 TEST CASE MẪU (TC02: Tra cứu lộ trình tuyến) ---")
        logs = run_react_agent(sample_query, provider, mcp_server)
        save_waterfall_trace(logs)
        print("\n💡 Hãy thử ngay lệnh: python src/app.py --interactive để chat trực tiếp!")
