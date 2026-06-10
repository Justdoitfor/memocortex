"""Embedding 工厂 — 本地 HuggingFace bge-small-zh-v1.5

懒加载: 第一次调用 get_embedder() 时下载/加载模型, 后续复用.
"""

from __future__ import annotations

from threading import Lock

from langchain_huggingface import HuggingFaceEmbeddings
from loguru import logger

from app.config import config

_embedder: HuggingFaceEmbeddings | None = None
_lock = Lock()


def get_embedder() -> HuggingFaceEmbeddings:
    """获取全局 Embedding 实例 — 单例, 线程安全, 懒加载.

    模型从 .env MEMOCORTEX_EMBEDDING_MODEL 配置, 默认 BAAI/bge-small-zh-v1.5 (512 维).
    """
    global _embedder
    if _embedder is None:
        with _lock:
            if _embedder is None:
                logger.info(f"加载 Embedding 模型: {config.embedding_model}")
                _embedder = HuggingFaceEmbeddings(
                    model_name=config.embedding_model,
                    model_kwargs={"device": "cpu"},
                    encode_kwargs={"normalize_embeddings": True},
                )
                logger.info("Embedding 模型加载完成")
    return _embedder


def embed_text(text: str) -> list[float]:
    """单条文本 → 向量, 便捷封装."""
    return get_embedder().embed_query(text)


def embed_batch(texts: list[str]) -> list[list[float]]:
    """批量文本 → 向量列表."""
    return get_embedder().embed_documents(texts)
