"""pytest 配置 + 共享 fixtures"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True, scope="session")
def _setup_logger() -> None:
    """测试统一关掉控制台日志, 避免污染输出."""
    from loguru import logger

    logger.remove()
