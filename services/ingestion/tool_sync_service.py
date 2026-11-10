import json

from services.mcp.amap_service import get_amap_tools
from services.retrieval.embedding import get_embeddings
from services.retrieval.tool_store import ToolStore


class ToolSyncService:
    """MCP 工具同步业务层。"""

    def __init__(self, store: ToolStore):
        self.store = store

    async def sync_amap(self, *, flush: bool = False) -> int:
        """同步高德 MCP 工具。"""
        tools_dict = await get_amap_tools()
        return await self.sync_server(
            server_name="amap_maps",
            tools=list(tools_dict.values()),
            flush=flush,
        )

    async def sync_server(
        self,
        *,
        server_name: str,
        tools: list,
        flush: bool = False,
    ) -> int:
        """同步一个 MCP Server 的工具。"""
        if not tools:
            return 0

        texts = [
            self._build_tool_text(tool, server_name)
            for tool in tools
        ]
        vectors = await get_embeddings().aembed_documents(texts)

        rows = []
        current_ids = set()

        for tool, text, vector in zip(tools, texts, vectors):
            tool_id = f"{server_name}:{tool.name}"
            current_ids.add(tool_id)

            rows.append({
                "tool_id": tool_id,
                "server_name": server_name,
                "tool_name": tool.name,
                "description": tool.description or "",
                "tool_schema": json.dumps(self._tool_schema(tool),
                    ensure_ascii=False,
                ),
                "search_text": text,
                "dense": vector,
            })

        for index in range(0, len(rows), 100):
            self.store.upsert(rows[index:index + 100])

        # 先 upsert 成功，再删该服务下已下线的工具
        old_ids = set(
            self.store.list_tool_ids(server_name=server_name)
        )
        stale_ids = old_ids - current_ids

        if stale_ids:
            self.store.delete(list(stale_ids))

        if flush:
            self.store.client.flush(self.store.collection_name)

        return len(rows)

    @staticmethod
    def _tool_schema(tool) -> dict:
        schema = getattr(tool, "args_schema", None) or {}

        if hasattr(schema, "model_json_schema"):
            return schema.model_json_schema()

        if isinstance(schema, str):
            try:
                return json.loads(schema)
            except json.JSONDecodeError:
                return {}

        if isinstance(schema, dict):
            return schema

        return {}

    @staticmethod
    def _build_tool_text(tool, server_name: str) -> str:
        schema = ToolSyncService._tool_schema(tool)
        properties = schema.get("properties") or {}
        required = set(schema.get("required") or [])

        param_lines = []
        for name, spec in properties.items():
            type_name = spec.get("type", "any")
            desc = (spec.get("description") or "").strip()
            flag = "必填" if name in required else "可选"
            param_lines.append(
                f"- {name}（{type_name}，{flag}）：{desc}"
            )

        return "\n".join([
            f"工具名: {tool.name}",
            f"所属服务: {server_name}",
            f"功能描述: {tool.description or ''}",
            "适用场景: 当用户的问题需要该工具提供的能力时使用。",
            "参数说明: ",
            *param_lines,
        ]).strip()
