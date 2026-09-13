"""
🔌 MULTI-PROVIDER LLM ADAPTER (Google Gemini, OpenAI & Offline Mock)
Hỗ trợ Native Tool Calling và chuyển đổi linh hoạt qua biến môi trường LLM_PROVIDER.
"""
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# load_dotenv() PHẢI chạy trước mọi os.getenv() ở cấp module,
# nếu không các biến khai trong .env sẽ đọc ra None.
load_dotenv()

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Mã tuyến hợp lệ: E01..E10 (Hà Nội), D4 (TP.HCM)
ROUTE_CODE_RE = re.compile(r"\b([ED]\d{1,2})\b", re.IGNORECASE)
OBS_ROUTE_RE = re.compile(r'"route_code":\s*"([ED]\d{1,2})"', re.IGNORECASE)
OBS_MATCHED_RE = re.compile(r'"matched_routes":\s*\[([^\]]*)\]')


def normalize_route_code(raw: Optional[str]) -> Optional[str]:
    """Chuẩn hoá 'e1' -> 'E01', 'd4' -> 'D4'. None nếu không hợp lệ."""
    if not raw:
        return None
    code = raw.strip().upper()
    if code.startswith("E") and len(code) == 2:
        code = f"E0{code[1]}"
    return code


def extract_route_code(text: str) -> Optional[str]:
    """Bóc mã tuyến đầu tiên ra khỏi câu hỏi tự nhiên."""
    m = ROUTE_CODE_RE.search(text or "")
    return normalize_route_code(m.group(1)) if m else None


class BaseLLMProvider:
    """Interface cơ sở cho các LLM Provider hỗ trợ Native Tool Calling"""

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        raise NotImplementedError

    def generate_with_tools(self, prompt: str, tools_schema: List[Dict[str, Any]],
                            system_prompt: str = "") -> Dict[str, Any]:
        raise NotImplementedError


class MockOfflineProvider(BaseLLMProvider):
    """Offline Mock Provider dùng để chạy thử mà không tốn API Key (mô phỏng ReAct đa bước)"""

    def __init__(self, fallback_reason: Optional[str] = None):
        self.model_name = "Offline-Mock-Model-2026"
        # Ghi lại lý do phải dùng Mock để trace phân biệt được live vs mock
        self.fallback_reason = fallback_reason

    def _tag(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload["engine"] = "mock"
        payload["fallback_reason"] = self.fallback_reason
        return payload

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        return (f"[Mock Chatbot Response]: Xin chào! Tôi đã nhận được câu hỏi '{prompt}'. "
                f"(Chế độ Chatbot không có Tool tra cứu dữ liệu thời gian thực).")

    def generate_with_tools(self, prompt: str, tools_schema: List[Dict[str, Any]],
                            system_prompt: str = "") -> Dict[str, Any]:
        prompt_lower = prompt.lower()

        # --- Trích xuất thực thể từ câu hỏi của hành khách ---
        route_code = extract_route_code(prompt)

        phone_match = re.search(r"0\d{9}", prompt)
        phone = phone_match.group(0) if phone_match else None

        month_match = re.search(r"\b(0?[1-9]|1[0-2])/(\d{4})\b", prompt)
        start_month = (f"{int(month_match.group(1)):02d}/{month_match.group(2)}"
                       if month_match else "10/2026")

        name_match = re.search(
            r"(?:cho|tên|anh|chị)\s+([A-ZĐÀ-Ỹ][a-zà-ỹ]+(?:\s+[A-ZĐÀ-Ỹ][a-zà-ỹ]+){1,3})",
            prompt,
        )
        passenger_name = name_match.group(1).strip() if name_match else "Khách hàng VinBus"

        # Loại vé theo đúng enum của tools.py (standard | priority | group | free)
        if any(k in prompt_lower for k in ["sinh viên", "học sinh", "công nhân"]):
            ticket_type = "priority"
        elif any(k in prompt_lower for k in ["người cao tuổi", "trên 60", "khuyết tật",
                                             "hộ nghèo", "người có công"]):
            ticket_type = "free"
        else:
            ticket_type = "standard"

        register_intent = any(k in prompt_lower for k in
                              ["đăng ký", "dang ky", "vé tháng", "ve thang", "mua vé"])
        lookup_intent = any(k in prompt_lower for k in
                            ["tra cứu", "lộ trình", "tuyến", "giờ", "giá vé", "điểm dừng"])
        has_observation = "[observation" in prompt_lower
        # Nhận biết đã đăng ký xong: dựa vào ticket_id trong Observation, không chỉ
        # dựa vào dòng Action (định dạng scratchpad có thể khác nhau giữa các bản).
        already_registered = ("register_monthly_ticket(" in prompt_lower
                              or '"ticket_id"' in prompt_lower)

        # --- Bước 2 trở đi: đã có Observation trong Scratchpad ---
        if has_observation:
            # ReAct đa bước: đã tra được mã tuyến -> tiến hành đăng ký vé tháng
            if register_intent and not already_registered:
                obs_match = OBS_ROUTE_RE.search(prompt)
                obs_code = normalize_route_code(obs_match.group(1)) if obs_match else None
                # Nếu khách đã nói rõ mã tuyến trong câu hỏi thì ưu tiên mã đó
                chosen = route_code or obs_code
                if chosen:
                    alts = self._parse_matched(prompt)
                    note = ""
                    if len(alts) > 1:
                        note = (f" Observation liệt kê {len(alts)} tuyến ({', '.join(alts)}), "
                                f"chọn {chosen} vì khớp cả điểm đi lẫn điểm đến.")
                    return self._tag({
                        "type": "tool_call",
                        "tool_name": "register_monthly_ticket",
                        "arguments": {
                            "passenger_name": passenger_name,
                            "phone_number": phone or "0900000000",
                            "route_code": chosen,
                            "start_month": start_month,
                            "ticket_type": ticket_type,
                        },
                        "thought": (f"Đã xác định được mã tuyến {chosen} từ Observation. "
                                    f"Tiếp tục gọi register_monthly_ticket để đăng ký vé tháng.{note}"),
                    })
            # Đã đủ dữ liệu -> chốt câu trả lời cuối cùng
            return self._tag({
                "type": "text",
                "content": "",  # Để rỗng -> app.py tự tổng hợp Final Answer từ Observation thật
                "thought": "Các Observation đã đủ thông tin, không cần gọi thêm Tool. Chốt Final Answer.",
            })

        # --- Bước 1: Đăng ký vé tháng ---
        if register_intent:
            if route_code:
                return self._tag({
                    "type": "tool_call",
                    "tool_name": "register_monthly_ticket",
                    "arguments": {
                        "passenger_name": passenger_name,
                        "phone_number": phone or "0900000000",
                        "route_code": route_code,
                        "start_month": start_month,
                        "ticket_type": ticket_type,
                    },
                    "thought": (f"Hành khách đã cung cấp đủ mã tuyến {route_code}, thông tin "
                                f"cá nhân và tháng bắt đầu. Gọi tool register_monthly_ticket."),
                })

            # Chưa có mã tuyến -> phải tra cứu lộ trình trước (ReAct đa bước)
            keyword = self._extract_leg(prompt)
            return self._tag({
                "type": "tool_call",
                "tool_name": "route_query",
                "arguments": {"query": keyword},
                "thought": (f"Hành khách muốn đăng ký vé tháng nhưng chưa cung cấp mã tuyến. "
                            f"Gọi route_query với từ khóa '{keyword}' để xác định mã tuyến trước."),
            })

        # --- Bước 1: Tra cứu lộ trình tuyến ---
        if route_code or lookup_intent:
            query = route_code or self._extract_leg(prompt)
            return self._tag({
                "type": "tool_call",
                "tool_name": "route_query",
                "arguments": {"query": query},
                "thought": (f"Hành khách muốn tra cứu thông tin tuyến "
                            f"{route_code or '(theo từ khóa địa điểm)'}. Tôi sẽ gọi tool route_query."),
            })

        # --- Câu hỏi kiến thức chung -> trả lời trực tiếp, không gọi Tool ---
        return self._tag({
            "type": "text",
            "content": (
                "[Mock Agent Response]: Xin chào! VinBus là hệ thống xe buýt điện của Vingroup, "
                "vận hành 100% bằng điện, có wifi và điều hòa miễn phí, hiện khai thác 10 tuyến "
                "có trợ giá E01-E10 tại Hà Nội. Hành khách có thể thanh toán bằng vé lượt mua "
                "trên xe, thẻ tháng VinBus, hoặc quẹt thẻ chip nội địa không tiếp xúc qua NAPAS."
            ),
            "thought": "Câu hỏi chung về dịch vụ VinBus, trả lời trực tiếp không cần gọi Tool.",
        })

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_matched(prompt: str) -> List[str]:
        """Lấy danh sách matched_routes từ Observation trong scratchpad."""
        m = OBS_MATCHED_RE.search(prompt)
        if not m:
            return []
        return re.findall(r'"([ED]\d{1,2})"', m.group(1))

    @staticmethod
    def _extract_leg(prompt: str) -> str:
        """Tách chặng 'từ A đến B' thành 'A - B' để route_query lọc đúng tuyến."""
        leg = re.search(
            r"từ\s+(.+?)\s+(?:đến|tới|ra|sang)\s+([^,\.\n]{3,40})", prompt, re.IGNORECASE
        )
        if leg:
            return f"{leg.group(1).strip()} - {leg.group(2).strip()}"
        return prompt.strip()


class GeminiProvider(BaseLLMProvider):
    """Google Gemini Provider (Native Tool Calling với Google GenAI SDK)"""

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gemini-2.5-flash"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            return "[Gemini Error]: Chưa cấu hình GEMINI_API_KEY trong file .env! Đang sử dụng chế độ Mock."
        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            contents = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            response = client.models.generate_content(model=self.model_name, contents=contents)
            return response.text
        except Exception as e:
            return f"[Gemini Exception]: {str(e)}"

    def generate_with_tools(self, prompt: str, tools_schema: List[Dict[str, Any]],
                            system_prompt: str = "") -> Dict[str, Any]:
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            print("ℹ️ [Gemini Provider]: Chưa tìm thấy GEMINI_API_KEY hợp lệ. Tự động chuyển sang Mock Offline.")
            return MockOfflineProvider("no_api_key").generate_with_tools(
                prompt, tools_schema, system_prompt)

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)

            # Chuẩn hóa function declarations cho Gemini SDK
            function_declarations = []
            for tool in tools_schema:
                if not tool.get("name") or not tool.get("parameters"):
                    continue
                function_declarations.append({
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {}),
                })

            config = types.GenerateContentConfig(
                system_instruction=system_prompt if system_prompt else None,
                tools=[{"function_declarations": function_declarations}] if function_declarations else None,
                temperature=0.2,
            )

            response = client.models.generate_content(
                model=self.model_name, contents=prompt, config=config
            )

            if response.function_calls:
                call = response.function_calls[0]
                args = dict(call.args) if getattr(call, "args", None) else {}
                return {
                    "type": "tool_call",
                    "tool_name": call.name,
                    "arguments": args,
                    "thought": (f"Gemini quyết định gọi công cụ '{call.name}' với tham số: "
                                f"{json.dumps(args, ensure_ascii=False)}"),
                    "engine": "live",
                    "model": self.model_name,
                }
            return {
                "type": "text",
                "content": response.text or "",
                "thought": "Gemini phản hồi trực tiếp bằng văn bản (không cần gọi công cụ).",
                "engine": "live",
                "model": self.model_name,
            }

        except Exception as e:
            reason = _classify_error(e)
            print(f"⚠️ [Gemini API Warning]: {reason['label']} → fallback về Mock.")
            if reason["kind"] == "quota_daily":
                print("   ↳ Đây là quota THEO NGÀY, chờ vài chục giây không có tác dụng. "
                      "Đổi LLM_MODEL sang model khác hoặc đợi reset lúc nửa đêm giờ Pacific.")
            return MockOfflineProvider(reason["kind"]).generate_with_tools(
                prompt, tools_schema, system_prompt)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI Provider (Native Tool Calling với OpenAI SDK)"""

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_openai_api_key_here":
            return "[OpenAI Error]: Chưa cấu hình OPENAI_API_KEY trong file .env! Đang sử dụng chế độ Mock."
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = client.chat.completions.create(model=self.model_name, messages=messages)
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"[OpenAI Exception]: {str(e)}"

    def generate_with_tools(self, prompt: str, tools_schema: List[Dict[str, Any]],
                            system_prompt: str = "") -> Dict[str, Any]:
        if not self.api_key or self.api_key == "your_openai_api_key_here":
            print("ℹ️ [OpenAI Provider]: Chưa tìm thấy OPENAI_API_KEY hợp lệ. Tự động chuyển sang Mock Offline.")
            return MockOfflineProvider("no_api_key").generate_with_tools(
                prompt, tools_schema, system_prompt)

        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)

            tools = []
            for tool in tools_schema:
                if not tool.get("name"):
                    continue
                tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {}),
                    },
                })

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
            )

            msg = response.choices[0].message
            if msg.tool_calls:
                call = msg.tool_calls[0]
                args = json.loads(call.function.arguments) if call.function.arguments else {}
                return {
                    "type": "tool_call",
                    "tool_name": call.function.name,
                    "arguments": args,
                    "thought": (f"OpenAI quyết định gọi công cụ '{call.function.name}' với tham số: "
                                f"{json.dumps(args, ensure_ascii=False)}"),
                    "engine": "live",
                    "model": self.model_name,
                }
            return {
                "type": "text",
                "content": msg.content or "",
                "thought": "OpenAI phản hồi trực tiếp bằng văn bản (không cần gọi công cụ).",
                "engine": "live",
                "model": self.model_name,
            }
        except Exception as e:
            reason = _classify_error(e)
            print(f"⚠️ [OpenAI API Warning]: {reason['label']} → fallback về Mock.")
            return MockOfflineProvider(reason["kind"]).generate_with_tools(
                prompt, tools_schema, system_prompt)


def _classify_error(e: Exception) -> Dict[str, str]:
    """Phân loại lỗi API để trace ghi lại được nguyên nhân fallback."""
    text = str(e)
    short = text[:160].replace("\n", " ")
    if "RESOURCE_EXHAUSTED" in text or "429" in text:
        if "PerDay" in text or "per day" in text.lower():
            return {"kind": "quota_daily", "label": "Hết quota THEO NGÀY (429 RESOURCE_EXHAUSTED)"}
        return {"kind": "quota_minute", "label": "Hết quota theo phút (429 RESOURCE_EXHAUSTED)"}
    if "No module named" in text:
        return {"kind": "sdk_missing", "label": f"Thiếu SDK ({short})"}
    if "API key" in text or "UNAUTHENTICATED" in text or "401" in text:
        return {"kind": "auth_error", "label": "API key không hợp lệ"}
    return {"kind": "unknown_error", "label": f"Lỗi không xác định ({short})"}


def get_llm_provider() -> BaseLLMProvider:
    """Factory function khởi tạo Provider theo LLM_PROVIDER env variable"""
    provider_type = os.getenv("LLM_PROVIDER", "gemini").lower()

    if provider_type == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        return GeminiProvider() if key and key != "your_gemini_api_key_here" else MockOfflineProvider("no_api_key")
    if provider_type == "openai":
        key = os.getenv("OPENAI_API_KEY")
        return OpenAIProvider() if key and key != "your_openai_api_key_here" else MockOfflineProvider("no_api_key")
    return MockOfflineProvider("provider_mock")


if __name__ == "__main__":
    mock = MockOfflineProvider("self_test")
    cases = [
        ("TC01", "Chào bạn, cho mình hỏi VinBus là dịch vụ gì?"),
        ("TC02", "Cho mình tra cứu lộ trình, giờ hoạt động và giá vé của tuyến xe buýt điện E01."),
        ("TC03", "Mình muốn đăng ký vé tháng tuyến E02 cho Trần Thị Bình, "
                 "số điện thoại 0987654321, bắt đầu từ tháng 10/2026 nhé."),
        ("TC04-s1", "Mình đi làm hằng ngày từ Vinhomes Ocean Park đến Bến xe Mỹ Đình. "
                    "Bạn tra giúp mình tuyến nào rồi đăng ký vé tháng luôn cho Nguyễn Minh Khôi, "
                    "số điện thoại 0912345678, bắt đầu từ tháng 10/2026."),
        ("TC05", "Cho mình xem lộ trình và giờ chạy của tuyến E99 với."),
    ]
    for tag, q in cases:
        r = mock.generate_with_tools(q, [])
        print(f"{tag:<9} {r['type']:<10} {r.get('tool_name', '-'):<24} {r.get('arguments', '')}")

    # TC04 bước 2: scratchpad đã có Observation
    scratch = (cases[3][1] + '\n[Observation]: {"status": "SUCCESS", "route_code": "E01", '
               '"matched_routes": ["E01", "E03"], "data": {}}')
    r = mock.generate_with_tools(scratch, [])
    print(f"{'TC04-s2':<9} {r['type']:<10} {r.get('tool_name', '-'):<24} {r.get('arguments', '')}")