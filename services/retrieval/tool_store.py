from typing import Any
from pymilvus import (
    MilvusClient,
    DataType,
    Function,
    FunctionType,
    AnnSearchRequest,
    RRFRanker,
    MilvusException
)
from config import settings
from functools import cache
import threading
import json

class ToolStore:
    """mcp工具长期记忆的 Milvus 数据访问层。"""

    def __init__(self, collection_name):
        self.collection_name = collection_name
        self.client = MilvusClient(
            uri=settings.MILVUS_URI,
            token=settings.MILVUS_TOKEN
        )
        self._ready = False
        self._lock = threading.Lock()

    def _build_schema(self):
        """构造 tool_store 的 schema"""
        schema = self.client.create_schema(enable_dynamic_field=True)
        # 业务主键 server_name:tool_name
        schema.add_field(
            field_name="tool_id",
            datatype=DataType.VARCHAR,
            max_length=512,
            is_primary=True,
        )
        schema.add_field(
            field_name="server_name",
            datatype=DataType.VARCHAR,
            max_length=128,
        )
        # 工具名称
        schema.add_field(
            field_name="tool_name",
            datatype=DataType.VARCHAR,
            max_length=255
        )
        # 工具描述
        schema.add_field(
            field_name="description",
            datatype=DataType.VARCHAR,
            max_length=4096,
        )
        # 工具的完整 JSON Schema（用于检索后动态绑定给 LLM）
        schema.add_field(
            field_name="tool_schema",
            datatype=DataType.VARCHAR,
            max_length=65535
        )
        # 稠密向量
        schema.add_field(
            field_name="dense",
            datatype=DataType.FLOAT_VECTOR,
            dim=1024
        )
        # 原始拼接文本（用于 BM25 自动生成稀疏向量，以及后续展示）
        schema.add_field(
            field_name="search_text",
            datatype=DataType.VARCHAR,
            enable_analyzer=True,
            analyzer_params={"type": "chinese"},
            max_length=65535
        )
        # 稀疏向量（由下方的 BM25 Function 自动生成）
        schema.add_field(
            field_name="sparse",
            datatype=DataType.SPARSE_FLOAT_VECTOR
        )
        # 添加 BM25 Function
        schema.add_function(Function(
            name="text_bm25_emb",
            function_type=FunctionType.BM25,
            input_field_names=["search_text"],
            output_field_names=["sparse"],
        ))
        return schema

    def _build_index_params(self):
        """构建索引"""
        index_params = self.client.prepare_index_params()
        # 稠密向量索引
        index_params.add_index(
            field_name="dense",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        # 稀疏向量索引
        index_params.add_index(
            field_name="sparse",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="BM25",
        )
        return index_params

    def ensure_collection(self) -> None:
        """幂等：不存在才创建，已存在只确保加载。"""
        if self._ready:
            return

        with self._lock:
            if self._ready:
                return

            if not self.client.has_collection(self.collection_name):
                try:
                    self.client.create_collection(
                        collection_name=self.collection_name,
                        schema=self._build_schema(),
                        index_params=self._build_index_params(),
                    )
                except MilvusException:
                    # 多进程同时启动时，可能已经被别的进程创建
                    if not self.client.has_collection(self.collection_name):
                        raise

            # 已有 Collection 在服务重启后可能未加载
            self.client.load_collection(self.collection_name)
            self._ready = True

    def insert(self, rows: list[dict[str, Any]]) -> dict:
        """插入数据"""
        self.ensure_collection()
        return self.client.insert(self.collection_name, rows)

    def upsert(self, rows: list[dict]) -> dict:
        """更新、写入数据"""
        self.ensure_collection()
        return self.client.upsert(self.collection_name, rows)

    def list_tool_ids(
        self,
        server_name: str | None = None,
    ) -> list[str]:
        """查询 tool_id，可按 MCP Server 过滤。"""
        self.ensure_collection()

        rows = self.client.query(
            collection_name=self.collection_name,
            filter=f"server_name == '{server_name}'",
            output_fields=["tool_id"],
        )
        return [row["tool_id"] for row in rows]

    def delete_by_server(self, server_name: str) -> dict:
        """删除某个 MCP Server 下的全部工具。"""
        self.ensure_collection()
        return self.client.delete(
            collection_name=self.collection_name,
            # 布尔表达式 默认None
            filter=f"server_name == '{server_name}'",
        )

    def delete(self, tool_ids: list[str]) -> dict:
        """按 tool_id 批量删除工具。"""
        if not tool_ids:
            return {"delete_count": 0}

        self.ensure_collection()
        total = 0
        for i in range(0, len(tool_ids), 100):
            result = self.client.delete(
                collection_name=self.collection_name,
                ids=tool_ids[i:i + 100],
            )
            total += result.get("delete_count", 0)

        return {"delete_count": total}

    def delete_all(self) -> dict:
        """删除全部工具，谨慎使用。"""
        tool_ids = self.list_tool_ids()
        return self.delete(tool_ids)

    def search_bm25(self, query: str, limit: int = 10):
        """BM25 检索，主要用于调试。"""
        self.ensure_collection()
        return self.client.search(
            collection_name=self.collection_name,
            data=[query],
            anns_field="sparse",
            search_params={"metric_type": "BM25"},
            limit=limit,
            output_fields=["tool_name", "tool_schema", "search_text"],
        )

    def search_dense(self, query_vector: list[float], limit: int = 10):
        """稠密向量检索，主要用于调试。"""
        self.ensure_collection()
        return self.client.search(
            collection_name=self.collection_name,
            data=[query_vector],
            anns_field="dense",
            search_params={"metric_type": "COSINE"},
            limit=limit,
            output_fields=["tool_name", "tool_schema", "search_text"],
        )

    def search_tools(self, query: str, query_vector: list[float], top_k: int) -> list[dict]:
        """混合检索RRF融合"""
        self.ensure_collection()
        reqs = [
            AnnSearchRequest(
                data=[query_vector],
                anns_field="dense",
                param={"metric_type": "COSINE"},
                limit=top_k,
            ),
            AnnSearchRequest(
                data=[query],
                anns_field="sparse",
                param={"metric_type": "BM25"},
                limit=top_k,
            ),
        ]
        hits = self.client.hybrid_search(
            collection_name=self.collection_name,
            reqs=reqs,
            ranker=RRFRanker(60),
            limit=top_k,
            output_fields=self._output_fields()
        )
        return [
            self._to_candidate(hit)
            for hit in (hits[0] if hits else [])
        ]

    @staticmethod
    def _to_candidate(hit: dict) -> dict:
        entity = hit.get("entity", {})
        raw_schema = entity.get("tool_schema") or "{}"

        try:
            # 反序列化
            input_schema = json.loads(raw_schema)
        except json.JSONDecodeError:
            input_schema = {}

        return {
            "tool_name": entity.get("tool_name", ""),
            "server_name": entity.get("server_name", ""),
            "description": entity.get("description", ""),
            "search_text": entity.get("search_text", ""),
            "schema": input_schema,
            "score": float(hit.get("distance", 0.0)),
        }

    @staticmethod
    def _output_fields() -> list[str]:
        return [
            "server_name",
            "tool_name",
            "description",
            "tool_schema",
            "search_text"
        ]

    def close(self) -> None:
        self.client.close()
        self._ready = False

@cache
def get_tool_store() -> ToolStore:
    """全进程复用一个 Store，不要每次请求 new MilvusClient。"""
    return ToolStore(
        collection_name="mcp_tools"
    )


def close_tool_store() -> None:
    """关闭工具库连接并清除工厂缓存。"""
    if get_tool_store.cache_info().currsize:
        get_tool_store().close()

    get_tool_store.cache_clear()