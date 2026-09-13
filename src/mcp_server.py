"""
🔌 MODEL CONTEXT PROTOCOL (MCP) SERVER MODULE
Mô phỏng kiến trúc MCP Server (Client-Server Architecture) cung cấp công cụ chuẩn hóa.
"""

import json
import sys
from typing import Dict, Any, List
from tools import TOOLS_SCHEMA, dispatch_tool_call

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


class MCPVinBusServer:
    """
    Giả lập MCP Server tuân thủ chuẩn giao thức Model Context Protocol
    phục vụ nghiệp vụ Chăm sóc Khách hàng VinBus.
    """
    def __init__(self, server_name: str = "vinbus-customer-mcp-server"):
        self.server_name = server_name
        self.version = "2026.1.0"

    def list_tools(self) -> List[Dict[str, Any]]:
        """Trả về danh sách các Tools chuẩn giao thức MCP"""
        return TOOLS_SCHEMA

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        [TASK 2.1 — ĐÃ HOÀN THÀNH] Thực thi request gọi Tool theo chuẩn MCP JSON-RPC 2.0

        Luồng xử lý:
        1. Chuyển yêu cầu xuống Tool Router (dispatch_tool_call) -> nhận về chuỗi JSON.
        2. Parse chuỗi JSON thành Python Dictionary.
        3. Đóng gói phản hồi theo đúng khung giao thức MCP JSON-RPC 2.0.
        """
        # Bước 1: Gọi Tool Router để thực thi công cụ thực tế
        raw_result = dispatch_tool_call(tool_name, arguments)

        # Bước 2: Parse chuỗi JSON trả về thành Dictionary (có xử lý lỗi an toàn)
        try:
            content = json.loads(raw_result)
        except (json.JSONDecodeError, TypeError) as e:
            content = {
                "status": "PARSE_ERROR",
                "error": f"Không parse được phản hồi JSON từ Tool '{tool_name}': {str(e)}",
                "raw": str(raw_result)
            }

        # Bước 3: Đóng gói phản hồi chuẩn giao thức MCP JSON-RPC 2.0
        return {
            "jsonrpc": "2.0",
            "server": self.server_name,
            "tool": tool_name,
            "result": content
        }


# Giữ alias tương thích ngược với tên lớp trong starter code
MCPAcademicServer = MCPVinBusServer

if __name__ == "__main__":
    print("==========================================================")
    print("🔌 KIỂM THỬ ĐỘC LẬP MCP SERVER (vinbus-customer-mcp-server)")
    print("==========================================================")

    server = MCPVinBusServer()
    tools = server.list_tools()
    print(f"✅ [MCP SERVER] Đã khởi tạo thành công {server.server_name} (Version: {server.version})")
    print(f"📦 Số lượng Tools công bố qua MCP: {len(tools)}")

    # Kiểm tra trạng thái TODO 1.2 (Tool Schema của công cụ hành động)
    action_tool = next((t for t in tools if t.get("name") == "register_monthly_ticket"), None)
    if action_tool and not action_tool.get("parameters", {}).get("properties"):
        print("⏳ [TODO 1.2]: Tool 'register_monthly_ticket' chưa được định nghĩa properties trong 'src/tools.py'.")
    else:
        props = list(action_tool["parameters"]["properties"].keys())
        print(f"✅ [TODO 1.2]: Tool 'register_monthly_ticket' đã có schema đầy đủ: {props}")
        print(f"   Tham số bắt buộc (required): {action_tool['parameters']['required']}")

    # Kiểm tra trạng thái TODO 2.1 (call_tool)
    test_result = server.call_tool("route_query", {"query": "VB01"})
    if not test_result:
        print("⏳ [TODO 2.1]: Hàm call_tool() đang trả về rỗng. Hãy hoàn thiện TODO 2.1 trong 'src/mcp_server.py'!")
    else:
        print("✅ [TODO 2.1]: Test dispatch tool 'route_query' thành công:")
        print(f"   Phản hồi JSON-RPC: {json.dumps(test_result, ensure_ascii=False)}")
