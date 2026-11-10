from typing import Any

from pymilvus import (
    MilvusClient,
    DataType,
    Function,
    FunctionType,
    AnnSearchRequest,
    RRFRanker,
    MilvusException,
)

from config import settings
from functools import cache
import threading


class ConversationStore:
    """会话长期记忆的 Milvus 数据访问层。"""

    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        self.client = MilvusClient(
            uri=settings.MILVUS_URI,
            token=settings.MILVUS_TOKEN,
        )
        self._ready = False
        self._lock = threading.Lock()

    def _build_schema(self):
        """构建 conversation_memory 的 schema。"""
        schema = self.client.create_schema(enable_dynamic_field=True)

        # 业务主键：thread_id:角色/内容哈希，保证同内容只写一次
        schema.add_field(
            field_name="memory_id",
            datatype=DataType.VARCHAR,
            max_length=1024,
            is_primary=True,
        )
        schema.add_field(
            field_name="thread_id",
            datatype=DataType.VARCHAR,
            max_length=512,
        )
        schema.add_field(
            field_name="user_id",
            datatype=DataType.VARCHAR,
            max_length=128,
        )
        # 单租户可以写空字符串
        schema.add_field(
            field_name="tenant_id",
            datatype=DataType.VARCHAR,
            max_length=128,
        )
        # 一轮对话的完整文本：用户 + 助手
        schema.add_field(
            field_name="content",
            datatype=DataType.VARCHAR,
            max_length=65535,
        )
        # 消息时间，Unix 毫秒
        schema.add_field(
            field_name="created_at",
            datatype=DataType.INT64,
        )
        # 稠密向量
        schema.add_field(
            field_name="dense",
            datatype=DataType.FLOAT_VECTOR,
            dim=settings.EMBEDDING_DIM,
        )
        # BM25 输入文本
        schema.add_field(
            field_name="search_text",
            datatype=DataType.VARCHAR,
            enable_analyzer=True,
            analyzer_params={"type": "chinese"},
            max_length=65535,
        )
        # BM25 Function 自动生成稀疏向量
        schema.add_field(
            field_name="sparse",
            datatype=DataType.SPARSE_FLOAT_VECTOR,
        )
        schema.add_function(Function(
            name="memory_bm25_emb",
            function_type=FunctionType.BM25,
            input_field_names=["search_text"],
            output_field_names=["sparse"],
        ))
        return schema

    def _build_index_params(self):
        """构建索引。"""
        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="dense",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
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

            self.client.load_collection(self.collection_name)
            self._ready = True

    def insert(self, rows: list[dict[str, Any]]) -> dict:
        """插入记忆。"""
        self.ensure_collection()
        return self.client.insert(self.collection_name, rows)

    def upsert(self, rows: list[dict]) -> dict:
        """写入或覆盖记忆。"""
        self.ensure_collection()
        return self.client.upsert(self.collection_name, rows)

    def list_memory_ids(
        self,
        user_id: str | None = None,
        thread_id: str | None = None,
    ) -> list[str]:
        """查询 memory_id，可按用户/会话过滤。"""
        self.ensure_collection()

        filters = []
        if user_id is not None:
            filters.append(f"user_id == '{user_id}'")
        if thread_id is not None:
            filters.append(f"thread_id == '{thread_id}'")

        rows = self.client.query(
            collection_name=self.collection_name,
            filter=" and ".join(filters),
            output_fields=["memory_id"],
            limit=16384,
        )
        return [row["memory_id"] for row in rows]

    def delete(self, memory_ids: list[str]) -> dict:
        """按 memory_id 批量删除。"""
        if not memory_ids:
            return {"delete_count": 0}

        self.ensure_collection()

        total = 0
        for i in range(0, len(memory_ids), 100):
            result = self.client.delete(
                collection_name=self.collection_name,
                ids=memory_ids[i:i + 100],
            )
            total += result.get("delete_count", 0)

        return {"delete_count": total}

    def delete_by_thread(self, thread_id: str) -> dict:
        """删除某个会话的全部记忆。"""
        self.ensure_collection()
        return self.client.delete(
            collection_name=self.collection_name,
            filter=f"thread_id == '{thread_id}'",
        )

    def delete_by_user(self, user_id: str) -> dict:
        """删除某个用户的全部记忆。"""
        self.ensure_collection()
        return self.client.delete(
            collection_name=self.collection_name,
            filter=f"user_id == '{user_id}'",
        )

    def delete_all(self) -> dict:
        """删除全部记忆，谨慎使用。"""
        return self.delete(self.list_memory_ids())

    def search_bm25(
        self,
        query: str,
        user_id: str,
        thread_id: str | None = None,
        limit: int = 10,
    ):
        """BM25 检索，主要用于调试。"""
        self.ensure_collection()
        return self.client.search(
            collection_name=self.collection_name,
            data=[query],
            anns_field="sparse",
            search_params={"metric_type": "BM25"},
            limit=limit,
            filter=self._build_filter(user_id, thread_id),
            output_fields=self._output_fields(),
        )

    def search_dense(
        self,
        query_vector: list[float],
        user_id: str,
        thread_id: str | None = None,
        limit: int = 10,
    ):
        """稠密向量检索，主要用于调试。"""
        self.ensure_collection()
        return self.client.search(
            collection_name=self.collection_name,
            data=[query_vector],
            anns_field="dense",
            search_params={"metric_type": "COSINE"},
            limit=limit,
            filter=self._build_filter(user_id, thread_id),
            output_fields=self._output_fields(),
        )

    def search_memorise(
        self,
        query: str,
        query_vector: list[float],
        user_id: str,
        thread_id: str | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        """混合检索 + RRF 融合。"""
        self.ensure_collection()

        expr = self._build_filter(user_id, thread_id)
        reqs = [
            AnnSearchRequest(
                data=[query_vector],
                anns_field="dense",
                param={"metric_type": "COSINE"},
                limit=top_k,
                expr=expr,
            ),
            AnnSearchRequest(
                data=[query],
                anns_field="sparse",
                param={"metric_type": "BM25"},
                limit=top_k,
                expr=expr,
            ),
        ]

        hits = self.client.hybrid_search(
            collection_name=self.collection_name,
            reqs=reqs,
            ranker=RRFRanker(60),
            limit=top_k,
            output_fields=self._output_fields(),
        )

        return [
            self._to_memory(hit)
            for hit in (hits[0] if hits else [])
        ]

    @staticmethod
    def _build_filter(
        user_id: str,
        thread_id: str | None,
    ) -> str:
        filters = [f"user_id == '{user_id}'"]
        if thread_id is not None:
            filters.append(
                f"thread_id == '{thread_id}'"
            )
        return " and ".join(filters)

    @staticmethod
    def _output_fields() -> list[str]:
        return [
            "memory_id", "thread_id", "user_id", "tenant_id",
            "content", "created_at", "search_text"
        ]

    @staticmethod
    def _to_memory(hit: dict) -> dict:
        entity = hit.get("entity", {})
        return {
            "memory_id": entity.get("memory_id", ""),
            "thread_id": entity.get("thread_id", ""),
            "user_id": entity.get("user_id", ""),
            "tenant_id": entity.get("tenant_id", ""),
            "content": entity.get("content", ""),
            "created_at": int(entity.get("created_at") or 0),
            "search_text": entity.get("search_text", ""),
            "score": float(hit.get("distance", 0.0)),
        }

    def close(self) -> None:
        self.client.close()
        self._ready = False

@cache
def get_conversation_store() -> ConversationStore:
    """全进程复用一个 Store，不要每次请求 new MilvusClient。"""
    return ConversationStore(
        collection_name="conversation_memory",
    )

def close_conversation_store() -> None:
    """关闭记忆库连接并清除工厂缓存。"""
    if get_conversation_store.cache_info().currsize:
        get_conversation_store().close()

    get_conversation_store.cache_clear()

