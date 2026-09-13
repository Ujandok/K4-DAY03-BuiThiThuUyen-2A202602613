"""
🛠️ TOOL DEFINITIONS & EXECUTION BACKEND
Mã nguồn chứa danh sách Tool Schemas (JSON Schema) và Execution Layer phục vụ cho MCP Server.
"""

import json
import re
import unicodedata
from typing import Any, Dict, List, Optional

# ==============================================================================
# 1. KHAI BÁO TOOL SCHEMAS CHUẨN NATIVE JSON SCHEMA (TASK 1.2)
# ==============================================================================

TOOLS_SCHEMA = [
    # Tool 1: Tra cứu lộ trình tuyến xe buýt điện
    {
        "name": "route_query",
        "description": (
            "Tra cứu thông tin lộ trình tuyến xe buýt điện VinBus: điểm đầu - điểm cuối, "
            "các điểm dừng chính, giờ hoạt động, tần suất và giá vé. "
            "Có thể tra theo mã tuyến (ví dụ 'E01') hoặc theo từ khóa điểm đi/điểm đến "
            "(ví dụ 'Ocean Park', 'Vinhomes Ocean Park - Bến xe Mỹ Đình'). "
            "Nếu nhiều tuyến cùng khớp, kết quả trả về danh sách trong 'matched_routes'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Mã tuyến cần tra cứu (ví dụ: 'E01') HOẶC từ khóa tên địa điểm "
                        "đi/đến để dò tìm tuyến phù hợp (ví dụ: 'Vinhomes Ocean Park'). "
                        "Chỉ truyền mã tuyến hoặc tên địa điểm, KHÔNG truyền nguyên câu "
                        "hỏi của hành khách."
                    )
                }
            },
            "required": ["query"]
        }
    },
    # --------------------------------------------------------------------------
    # TASK 1.2  — TOOL SCHEMA CHO HÀNH ĐỘNG 'register_monthly_ticket'
    # --------------------------------------------------------------------------
    {
        "name": "register_monthly_ticket",
        "description": (
            "Đăng ký vé tháng cho hành khách trên một tuyến xe buýt điện VinBus cụ thể. "
            "Bắt buộc phải có mã tuyến hợp lệ. Nếu khách hàng chỉ mô tả điểm đi/điểm đến "
            "mà chưa cung cấp mã tuyến, hãy gọi công cụ 'route_query' để xác định mã tuyến "
            "trước, tuyệt đối không tự suy đoán mã tuyến."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "passenger_name": {
                    "type": "string",
                    "description": "Họ và tên đầy đủ của hành khách đăng ký vé tháng (ví dụ: 'Nguyễn Minh Khôi')"
                },
                "phone_number": {
                    "type": "string",
                    "description": "Số điện thoại liên hệ của hành khách, gồm 10 chữ số (ví dụ: '0912345678')"
                },
                "route_code": {
                    "type": "string",
                    "description": "Mã tuyến xe buýt điện đăng ký vé tháng (ví dụ: 'E01'), lấy từ kết quả 'route_query'"
                },
                "start_month": {
                    "type": "string",
                    "description": "Tháng bắt đầu sử dụng vé theo định dạng MM/YYYY (ví dụ: '10/2026')"
                },
                "ticket_type": {
                    "type": "string",
                    "enum": ["standard", "priority", "group", "free"],
                    "description": (
                        "Loại vé tháng theo QĐ 5290/QĐ-UBND: "
                        "'standard' (khách thường, 140.000đ), "
                        "'priority' (học sinh, sinh viên, công nhân KCN, 70.000đ), "
                        "'group' (mua tập thể từ 30 người, 100.000đ), "
                        "'free' (người có công, người cao tuổi từ 60, người khuyết tật, "
                        "trẻ em dưới 6 tuổi, hộ nghèo - miễn phí). Mặc định 'standard'."
                    )
                }
            },
            "required": ["passenger_name", "phone_number", "route_code", "start_month"]
        }
    }
]

# ==============================================================================
# 2. MÔ PHỎNG DỮ LIỆU
# ==============================================================================
# MOCK_ROUTE_DATABASE - Dữ liệu các tuyến buýt điện VinBus (cập nhật 09/2026)
#
# Nguồn: vinbus.vn, QĐ 5290/QĐ-UBND (giá vé hiệu lực 01/11/2024).
# Vé lượt theo cự ly: <15km 8.000 | 15-25km 10.000 | 25-30km 12.000
#                     | 30-40km 15.000 | >=40km 20.000
# Thẻ tháng 1 tuyến: 140.000 (thường) / 70.000 (ưu tiên) / 100.000 (tập thể)
#
# LƯU Ý: tên tuyến, điểm đầu - cuối và giá vé là số liệu thật.
# Riêng operating_hours / frequency_minutes là giá trị gần đúng.

MOCK_ROUTE_DATABASE = {
    "E01": {
        "route_name": "Bến xe Mỹ Đình - Ngã Tư Sở - KĐT Vinhomes Ocean Park",
        "origin": "Bến xe Mỹ Đình (Nam Từ Liêm)",
        "destination": "KĐT Vinhomes Ocean Park (Gia Lâm)",
        "main_stops": ["Bến xe Mỹ Đình", "Phạm Hùng", "Khuất Duy Tiến", "Ngã Tư Sở",
                       "Trường Chinh", "Cầu Vĩnh Tuy", "Cổ Linh", "KĐT Ocean Park"],
        "operating_hours": "05:00 - 21:00",
        "frequency_minutes": 20,
        "single_fare_vnd": 12000,
        "monthly_fare_vnd": 140000,
        "status": "Đang khai thác"
    },
    "E02": {
        "route_name": "Hào Nam - Long Biên - KĐT Vinhomes Ocean Park",
        "origin": "Hào Nam (Ga Cát Linh, Đống Đa)",
        "destination": "KĐT Vinhomes Ocean Park (Gia Lâm)",
        "main_stops": ["Hào Nam (Ga Cát Linh)", "Kim Mã", "Phan Đình Phùng",
                       "Điểm trung chuyển Long Biên", "Cầu Chương Dương",
                       "Nguyễn Văn Cừ", "Sài Đồng", "KĐT Ocean Park"],
        "operating_hours": "05:00 - 22:00",
        "frequency_minutes": 20,
        "single_fare_vnd": 12000,
        "monthly_fare_vnd": 140000,
        "status": "Đang khai thác"
    },
    "E03": {
        "route_name": "Bến xe Mỹ Đình (Hàm Nghi) - Thái Hà - KĐT Vinhomes Ocean Park",
        "origin": "Bến xe Mỹ Đình - Hàm Nghi (Nam Từ Liêm)",
        "destination": "KĐT Vinhomes Ocean Park (Gia Lâm)",
        "main_stops": ["Mỹ Đình (Hàm Nghi)", "Phạm Hùng", "Trần Duy Hưng",
                       "Nguyễn Chí Thanh", "Thái Hà", "Xã Đàn", "Cầu Vĩnh Tuy",
                       "Cổ Linh", "KĐT Ocean Park"],
        "operating_hours": "05:00 - 21:00",
        "frequency_minutes": 20,
        "single_fare_vnd": 15000,
        "monthly_fare_vnd": 140000,
        "status": "Đang khai thác"
    },
    "E04": {
        "route_name": "Vincom Long Biên - KĐT Vinhomes Smart City",
        "origin": "Vincom Long Biên (Long Biên)",
        "destination": "KĐT Vinhomes Smart City (Nam Từ Liêm)",
        "main_stops": ["Vincom Long Biên", "Cầu Chương Dương", "Trần Nhật Duật",
                       "Kim Mã", "Cầu Giấy", "Đại lộ Thăng Long", "KĐT Smart City"],
        "operating_hours": "05:00 - 21:00",
        "frequency_minutes": 20,
        "single_fare_vnd": 12000,
        "monthly_fare_vnd": 140000,
        "status": "Đang khai thác"
    },
    "E05": {
        "route_name": "Long Biên - Cầu Giấy - KĐT Vinhomes Smart City",
        "origin": "Điểm trung chuyển Long Biên (Ba Đình)",
        "destination": "KĐT Vinhomes Smart City (Nam Từ Liêm)",
        "main_stops": ["Long Biên", "Yên Phụ", "Thanh Niên", "Kim Mã",
                       "Cầu Giấy", "Xuân Thủy", "Hồ Tùng Mậu", "KĐT Smart City"],
        "operating_hours": "05:00 - 21:00",
        "frequency_minutes": 20,
        "single_fare_vnd": 10000,
        "monthly_fare_vnd": 140000,
        "status": "Đang khai thác"
    },
    "E06": {
        "route_name": "Bến xe Giáp Bát - Bến xe Nước Ngầm - KĐT Vinhomes Smart City",
        "origin": "Bến xe Giáp Bát (Hoàng Mai)",
        "destination": "KĐT Vinhomes Smart City (Nam Từ Liêm)",
        "main_stops": ["Bến xe Giáp Bát", "Bến xe Nước Ngầm", "Giải Phóng",
                       "Trường Chinh", "Khuất Duy Tiến", "Đại lộ Thăng Long",
                       "KĐT Smart City"],
        "operating_hours": "05:00 - 21:00",
        "frequency_minutes": 20,
        "single_fare_vnd": 10000,
        "monthly_fare_vnd": 140000,
        "status": "Đang khai thác"
    },
    "E07": {
        "route_name": "Long Biên - Cửa Nam - KĐT Vinhomes Smart City",
        "origin": "Điểm trung chuyển Long Biên (Ba Đình)",
        "destination": "KĐT Vinhomes Smart City (Nam Từ Liêm)",
        "main_stops": ["Long Biên", "Hàng Đậu", "Cửa Nam", "Nguyễn Thái Học",
                       "Kim Mã", "Lê Đức Thọ", "KĐT Smart City"],
        "operating_hours": "05:00 - 21:00",
        "frequency_minutes": 20,
        "single_fare_vnd": 10000,
        "monthly_fare_vnd": 140000,
        "status": "Đang khai thác"
    },
    "E08": {
        "route_name": "Khu Liên cơ Sở ngành Hà Nội - Khu Ngoại giao đoàn - KĐT Times City",
        "origin": "Khu Liên cơ quan Sở ngành Hà Nội (Võ Chí Công, Tây Hồ)",
        "destination": "KĐT Times City (Hai Bà Trưng)",
        "main_stops": ["Khu Liên cơ Sở ngành Hà Nội", "Khu Ngoại giao đoàn",
                       "Võ Chí Công", "Xuân Thủy", "Láng", "Đại Cồ Việt",
                       "KĐT Times City"],
        "operating_hours": "05:00 - 21:00",
        "frequency_minutes": 20,
        "single_fare_vnd": 10000,
        "monthly_fare_vnd": 140000,
        "status": "Đang khai thác"
    },
    "E09": {
        "route_name": "KĐT Vinhomes Smart City - Khu Liên cơ quan Sở ngành Hà Nội",
        "origin": "KĐT Vinhomes Smart City (Nam Từ Liêm)",
        "destination": "Khu Liên cơ quan Sở ngành Hà Nội (Võ Chí Công, Tây Hồ)",
        "main_stops": ["KĐT Smart City", "Đại lộ Thăng Long", "Trần Duy Hưng",
                       "Nguyễn Chí Thanh", "Đào Tấn", "Võ Chí Công",
                       "Khu Liên cơ quan Sở ngành Hà Nội"],
        "operating_hours": "05:00 - 21:00",
        "frequency_minutes": 20,
        "single_fare_vnd": 10000,
        "monthly_fare_vnd": 140000,
        "status": "Đang khai thác (điều chỉnh lộ trình từ 01/01/2024)"
    },
    "E10": {
        "route_name": "KĐT Vinhomes Ocean Park - Cảng HKQT Nội Bài",
        "origin": "KĐT Vinhomes Ocean Park (Gia Lâm)",
        "destination": "Sân bay Nội Bài - Nhà ga T1 & T2 (Sóc Sơn)",
        "main_stops": ["KĐT Ocean Park", "Lý Thánh Tông", "Cổ Linh", "Nguyễn Văn Cừ",
                       "Cầu Đông Trù", "Trường Sa", "Võ Nguyên Giáp",
                       "Nhà ga T1 (bãi P2)", "Nhà ga T2 (bãi P6)"],
        "operating_hours": "05:00 - 21:00",
        "frequency_minutes": 30,
        "single_fare_vnd": 20000,
        "monthly_fare_vnd": 140000,
        "status": "Đang khai thác (vận hành từ 01/01/2024)"
    },
    "D4": {
        "route_name": "Vinhomes Grand Park - Bến xe buýt Sài Gòn",
        "origin": "Vinhomes Grand Park (TP. Thủ Đức, TP.HCM)",
        "destination": "Bến xe buýt Sài Gòn (Quận 1, TP.HCM)",
        "main_stops": ["Vinhomes Grand Park", "Khu Công nghệ cao (SHTP)",
                       "Đảo Kim Cương", "KĐT Sala", "Chợ Dân Sinh",
                       "Trạm trung chuyển Hàm Nghi", "Bến xe buýt Sài Gòn"],
        "operating_hours": "05:00 - 21:00",
        "frequency_minutes": 20,
        "single_fare_vnd": 7000,
        "monthly_fare_vnd": 157500,
        "status": "Đang khai thác (tuyến buýt điện có trợ giá duy nhất tại TP.HCM)"
    }
}

# ------------------------------------------------------------------
# Bảng giá
# ------------------------------------------------------------------
SINGLE_FARE_BY_DISTANCE_VND = [
    (0, 15, 8000),
    (15, 25, 10000),
    (25, 30, 12000),
    (30, 40, 15000),
    (40, None, 20000),
]

SINGLE_FARE_BY_ROUTE_VND = {
    "E01": 12000, "E02": 12000, "E03": 15000, "E04": 12000, "E05": 10000,
    "E06": 10000, "E07": 10000, "E08": 10000, "E09": 10000, "E10": 20000,
    "D4": 7000,
}

MONTHLY_PASS_VND = {
    "priority": {"single_route": 70000, "multi_route": 140000},
    "group": {"single_route": 100000, "multi_route": 200000},
    "standard": {"single_route": 140000, "multi_route": 280000},
}

CARD_ISSUE_FEE_VND = 60000

FREE_FARE_GROUPS = {
    "nguoi_co_cong": "Người có công với cách mạng",
    "nguoi_cao_tuoi": "Người cao tuổi từ 60 tuổi trở lên",
    "nguoi_khuyet_tat": "Người khuyết tật",
    "tre_em_duoi_6": "Trẻ em dưới 6 tuổi",
    "ho_ngheo": "Nhân khẩu thuộc hộ nghèo",
}

# LLM hay sinh ra tên loại vé theo thói quen ('student', 'senior'...).
# Bảng này quy về đúng 4 nhóm của QĐ 5290 để không tính sai giá.
TICKET_TYPE_ALIASES = {
    "standard": "standard", "normal": "standard", "adult": "standard",
    "pho_thong": "standard", "thuong": "standard",
    "priority": "priority", "student": "priority", "pupil": "priority",
    "worker": "priority", "uu_tien": "priority", "hssv": "priority",
    "group": "group", "collective": "group", "tap_the": "group",
    "free": "free", "senior": "free", "elderly": "free",
    "disabled": "free", "child": "free", "mien_phi": "free",
    **{k: "free" for k in FREE_FARE_GROUPS},
}

HCMC_FARE_VND = {"standard": 7000, "student": 3000, "ticket_book_30": 157500}


def normalize_ticket_type(ticket_type: Optional[str]) -> str:
    """Quy mọi biến thể tên loại vé về 1 trong 4 nhóm hợp lệ."""
    key = (ticket_type or "standard").strip().lower().replace(" ", "_")
    return TICKET_TYPE_ALIASES.get(key, "standard")


def get_single_fare(route_id: str, passenger_type: str = "standard") -> int:
    """Trả về giá vé lượt (VNĐ) cho một tuyến và loại hành khách."""
    ptype = normalize_ticket_type(passenger_type)
    if ptype == "free":
        return 0
    if route_id == "D4":
        return HCMC_FARE_VND["student" if ptype == "priority" else "standard"]
    # Hà Nội: vé lượt đồng hạng, không phân biệt loại hành khách
    return SINGLE_FARE_BY_ROUTE_VND[route_id]


def get_fare_by_distance(distance_km: float) -> int:
    """Trả về giá vé lượt (VNĐ) theo cự ly tuyến - khung giá Hà Nội."""
    for low, high, fare in SINGLE_FARE_BY_DISTANCE_VND:
        if distance_km >= low and (high is None or distance_km < high):
            return fare
    raise ValueError(f"Cự ly không hợp lệ: {distance_km}")


def get_monthly_pass(passenger_type: str = "standard",
                     multi_route: bool = False) -> int:
    """Trả về giá vé tháng (VNĐ). passenger_type: standard | priority | group | free."""
    ptype = normalize_ticket_type(passenger_type)
    if ptype == "free":
        return 0
    key = "multi_route" if multi_route else "single_route"
    return MONTHLY_PASS_VND[ptype][key]


# ==============================================================================
# 3. CHUẨN HOÁ ĐẦU VÀO CHO route_query
# ==============================================================================

ROUTE_CODE_RE = re.compile(r"\b([ED]\d{1,2})\b", re.IGNORECASE)

# Các từ nối chỉ hướng đi, dùng để tách "từ A đến B" thành ['A', 'B']
_SPLIT_RE = re.compile(
    r"\s*(?:[-–—>→,]|\bđến\b|\btới\b|\bsang\b|\bra\b)\s*", re.IGNORECASE
)

# Cụm từ thừa trong câu hỏi tự nhiên, bỏ đi trước khi dò địa danh
_FILLER_RE = re.compile(
    r"\b(cho|mình|tôi|em|bạn|xem|tra|cứu|giúp|hỏi|với|nhé|ạ|là|của|và|"
    r"lộ|trình|giờ|chạy|hoạt|động|giá|vé|tuyến|xe|buýt|điện|vinbus|"
    r"thông|tin|chi|tiết|muốn|biết|đi|làm|hằng|ngày|từ|hết|bao|nhiêu)\b",
    re.IGNORECASE,
)


def _norm(text: str) -> str:
    """Chuẩn hoá unicode + lowercase + gộp khoảng trắng."""
    text = unicodedata.normalize("NFC", text or "")
    return re.sub(r"\s+", " ", text).strip().lower()


def _tokens(text: str) -> set:
    """Tách thành tập token để so khớp theo từ, không theo chuỗi con."""
    return set(re.findall(r"\w+", _norm(text), flags=re.UNICODE))


def _haystack(info: Dict[str, Any]) -> set:
    return _tokens(" ".join(
        [info["route_name"], info["origin"], info["destination"]] + info["main_stops"]
    ))


def extract_route_code(query: str) -> Optional[str]:
    """Bóc mã tuyến (E01, D4...) ra khỏi câu hỏi tự nhiên. None nếu không có."""
    for m in ROUTE_CODE_RE.finditer(query or ""):
        raw = m.group(1).upper()
        # chuẩn hoá E1 -> E01, giữ nguyên D4
        if raw.startswith("E") and len(raw) == 2:
            raw = f"E0{raw[1]}"
        return raw
    return None


def extract_places(query: str) -> List[str]:
    """Tách câu hỏi thành danh sách địa danh để dò tuyến."""
    cleaned = _FILLER_RE.sub(" ", _norm(query))
    parts = [re.sub(r"[^\w\sÀ-ỹ]", " ", p) for p in _SPLIT_RE.split(cleaned)]
    parts = [re.sub(r"\s+", " ", p).strip() for p in parts]
    # bỏ mảnh quá ngắn (nhiễu) - địa danh thật luôn >= 3 ký tự
    return [p for p in parts if len(p) >= 3]


def find_routes(query: str) -> List[str]:
    """Trả về danh sách mã tuyến khớp, ưu tiên mã tuyến rồi mới đến địa danh."""
    code = extract_route_code(query)
    if code and code in MOCK_ROUTE_DATABASE:
        return [code]

    places = extract_places(query)
    if not places:
        return []

    # Tuyến hợp lệ phải chứa TẤT CẢ địa danh trong query
    # (so khớp theo tập token, nên 'Bến xe Mỹ Đình' vẫn khớp dù 'xe' bị lọc)
    matched = [
        code for code, info in MOCK_ROUTE_DATABASE.items()
        if all(_tokens(p) <= _haystack(info) for p in places)
    ]
    if matched:
        return matched

    # Nới lỏng: chấp nhận tuyến khớp ít nhất 1 địa danh
    return [
        code for code, info in MOCK_ROUTE_DATABASE.items()
        if any(_tokens(p) <= _haystack(info) for p in places)
    ]


# ==============================================================================
# 4. EXECUTION LAYER
# ==============================================================================

def execute_route_query(query: str) -> str:
    """Thực thi tra cứu tuyến xe buýt điện theo mã tuyến hoặc từ khóa địa điểm."""
    matched = find_routes(query or "")

    if not matched:
        return json.dumps({
            "status": "NOT_FOUND",
            "message": f"Không tìm thấy tuyến xe buýt điện VinBus nào khớp với '{query}'",
            "available_routes": list(MOCK_ROUTE_DATABASE.keys()),
        }, ensure_ascii=False)

    primary = matched[0]
    return json.dumps({
        "status": "SUCCESS",
        "route_code": primary,
        "matched_routes": matched,
        "data": MOCK_ROUTE_DATABASE[primary],
        "note": (
            f"Có {len(matched)} tuyến cùng khớp ({', '.join(matched)}), "
            f"đang trả về {primary}. Hãy nêu các lựa chọn còn lại cho hành khách."
        ) if len(matched) > 1 else None,
    }, ensure_ascii=False)


def execute_register_monthly_ticket(
    passenger_name: str,
    phone_number: str,
    route_code: str,
    start_month: str,
    ticket_type: str = "standard"
) -> str:
    """Thực thi đăng ký vé tháng cho hành khách trên một tuyến VinBus."""
    code = extract_route_code(route_code) or (route_code or "").strip().upper()
    route = MOCK_ROUTE_DATABASE.get(code)

    # Không cho phép đăng ký vé trên tuyến không tồn tại (Anti-Hallucination)
    if not route:
        return json.dumps({
            "status": "NOT_FOUND",
            "message": (
                f"Không thể đăng ký vé tháng: mã tuyến '{route_code}' không tồn tại "
                f"trong hệ thống VinBus."
            ),
            "available_routes": list(MOCK_ROUTE_DATABASE.keys()),
        }, ensure_ascii=False)

    # Validate số điện thoại
    phone = re.sub(r"\D", "", phone_number or "")
    if len(phone) != 10 or not phone.startswith("0"):
        return json.dumps({
            "status": "VALIDATION_ERROR",
            "message": (
                f"Số điện thoại '{phone_number}' không hợp lệ. "
                f"Cần đúng 10 chữ số và bắt đầu bằng 0."
            ),
        }, ensure_ascii=False)

    # Validate tháng bắt đầu MM/YYYY
    if not re.fullmatch(r"(0[1-9]|1[0-2])/\d{4}", (start_month or "").strip()):
        return json.dumps({
            "status": "VALIDATION_ERROR",
            "message": (
                f"Tháng bắt đầu '{start_month}' không hợp lệ. "
                f"Cần định dạng MM/YYYY, ví dụ '10/2026'."
            ),
        }, ensure_ascii=False)

    ttype = normalize_ticket_type(ticket_type)
    price = get_monthly_pass(passenger_type=ttype, multi_route=False)

    if ttype == "free":
        message = (
            f"{passenger_name} ({phone}) thuộc nhóm được miễn phí vé xe buýt. "
            f"Không cần mua vé tháng tuyến {code} - {route['route_name']}; "
            f"vui lòng làm thẻ miễn phí không thời hạn tại điểm bán vé."
        )
    else:
        message = (
            f"Đăng ký vé tháng thành công cho {passenger_name} ({phone}) "
            f"trên tuyến {code} - {route['route_name']}, bắt đầu từ tháng {start_month}, "
            f"loại vé '{ttype}', phí tem tháng {price:,} VNĐ "
            f"(chưa gồm phí phát hành thẻ {CARD_ISSUE_FEE_VND:,} VNĐ thu một lần)."
        )

    return json.dumps({
        "status": "SUCCESS",
        "ticket_id": f"VB-{code}-{phone[-4:]}",
        "passenger_name": passenger_name,
        "phone_number": phone,
        "route_code": code,
        "route_name": route["route_name"],
        "start_month": start_month,
        "ticket_type": ttype,
        "ticket_type_requested": ticket_type,
        "price_vnd": price,
        "card_issue_fee_vnd": 0 if ttype == "free" else CARD_ISSUE_FEE_VND,
        "message": message,
    }, ensure_ascii=False)


# Router gọi tool thực tế
TOOL_ROUTER = {
    "route_query": execute_route_query,
    "register_monthly_ticket": execute_register_monthly_ticket
}


def dispatch_tool_call(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Hàm trung chuyển thực thi tool."""
    if tool_name in TOOL_ROUTER:
        try:
            return TOOL_ROUTER[tool_name](**arguments)
        except TypeError as e:
            return json.dumps({
                "status": "VALIDATION_ERROR",
                "error": f"Sai tham số khi gọi '{tool_name}': {e}",
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "status": "EXECUTION_ERROR",
                "error": str(e),
            }, ensure_ascii=False)
    return json.dumps({
        "status": "UNKNOWN_TOOL",
        "error": f"Tool '{tool_name}' không tồn tại!",
    }, ensure_ascii=False)


# ==============================================================================
# 5. SELF-TEST
# ==============================================================================
if __name__ == "__main__":
    checks = [
        # (mô tả, input, kỳ vọng)
        ("TC05 - câu hỏi tự nhiên có mã tuyến",
         "Cho mình xem lộ trình và giờ chạy của tuyến E07 với.", "SUCCESS"),
        ("TC04 - chặng đi/đến",
         "Vinhomes Ocean Park - Bến xe Mỹ Đình", "SUCCESS"),
        ("Mã tuyến không tồn tại", "E99", "NOT_FOUND"),
        ("Địa danh đơn", "Ocean Park", "SUCCESS"),
        ("Câu đầy đủ", "từ Vinhomes Ocean Park đến Bến xe Mỹ Đình", "SUCCESS"),
    ]
    for desc, q, expected in checks:
        res = json.loads(execute_route_query(q))
        ok = "✅" if res["status"] == expected else "❌"
        print(f"{ok} {desc:<40} -> {res['status']:<10} "
              f"{res.get('matched_routes', res.get('available_routes', ''))}")

    print()
    print(json.loads(execute_register_monthly_ticket(
        "Trần Thị Bình", "0987654321", "E02", "10/2026", "student"))["price_vnd"])
    print(json.loads(execute_register_monthly_ticket(
        "Lê Văn C", "0900000001", "E05", "10/2026", "senior"))["price_vnd"])
    print(json.loads(execute_register_monthly_ticket(
        "Sai SĐT", "123", "E05", "10/2026"))["status"])