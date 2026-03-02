"""
PDF Knowledge Store Preload State

백그라운드에서 진행되는 PDF 프리로딩 상태를 추적합니다.
서버 기동 직후 모든 제품의 StructuredKnowledgeStore를 미리 파싱하여
첫 쿼리의 cold start 지연(~5분)을 제거합니다.
"""
import time
import threading
from typing import Optional


class PreloadState:
    """Thread-safe preload progress tracker"""

    def __init__(self):
        self._lock = threading.Lock()
        self.total: int = 0
        self.loaded: int = 0
        self.current_product: str = ""
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.error: Optional[str] = None

    @property
    def is_running(self) -> bool:
        return self.started_at is not None and self.finished_at is None

    @property
    def is_done(self) -> bool:
        return self.finished_at is not None

    @property
    def elapsed_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at or time.time()
        return round(end - self.started_at, 1)

    def start(self, total: int):
        with self._lock:
            self.total = total
            self.loaded = 0
            self.started_at = time.time()

    def update(self, product_id: str):
        with self._lock:
            self.current_product = product_id

    def advance(self):
        with self._lock:
            self.loaded += 1

    def finish(self, error: Optional[str] = None):
        with self._lock:
            self.finished_at = time.time()
            self.error = error

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "total": self.total,
                "loaded": self.loaded,
                "current_product": self.current_product,
                "is_running": self.is_running,
                "is_done": self.is_done,
                "elapsed_seconds": self.elapsed_seconds,
                "error": self.error,
            }


# Global singleton
_state = PreloadState()


def get_preload_state() -> PreloadState:
    return _state
