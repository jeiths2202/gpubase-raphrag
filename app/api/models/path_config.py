"""
Path Configuration Model

Centralized file system path settings.
Environment variable prefix: PATH_, KMS_DATA_ROOT

Usage:
    from app.api.services.configuration_service import get_path_config
    config = get_path_config()
    uploads_path = config.get_absolute_path('uploads_dir')
"""

from pathlib import Path
from pydantic import BaseModel, Field


class PathConfig(BaseModel):
    """
    파일 시스템 경로 설정.

    data_root를 기준으로 상대 경로를 관리하며,
    절대 경로 변환 및 디렉토리 자동 생성 기능을 제공합니다.
    """

    # ─────────────────────────────────────────────────────────────────
    # Root Directory
    # ─────────────────────────────────────────────────────────────────
    data_root: str = Field(
        default="/opt/kms",
        description="KMS data root directory",
        json_schema_extra={
            "env_var": "KMS_DATA_ROOT",
            "effect": "All relative paths are resolved from this root",
            "category": "root"
        }
    )

    # ─────────────────────────────────────────────────────────────────
    # Relative Paths (auto-joined with data_root)
    # ─────────────────────────────────────────────────────────────────
    uploads_dir: str = Field(
        default="uploads",
        description="Upload storage directory (relative to data_root)",
        json_schema_extra={
            "env_var": "PATH_UPLOADS",
            "category": "storage"
        }
    )
    summaries_dir: str = Field(
        default="uploads/summaries",
        description="Summary files directory (relative to data_root)",
        json_schema_extra={
            "env_var": "PATH_SUMMARIES",
            "effect": "BM25 summary files and indexes",
            "category": "storage"
        }
    )
    models_dir: str = Field(
        default="models",
        description="ML models directory (relative to data_root)",
        json_schema_extra={
            "env_var": "PATH_MODELS",
            "category": "models"
        }
    )
    qlora_adapters_dir: str = Field(
        default="models/qlora_adapters",
        description="QLoRA adapters directory (relative to data_root)",
        json_schema_extra={
            "env_var": "PATH_QLORA_ADAPTERS",
            "effect": "Fine-tuned LoRA adapter weights",
            "category": "models"
        }
    )
    training_data_dir: str = Field(
        default="data/training",
        description="Training data directory (relative to data_root)",
        json_schema_extra={
            "env_var": "PATH_TRAINING_DATA",
            "effect": "QA pairs and training datasets",
            "category": "data"
        }
    )
    logs_dir: str = Field(
        default="logs",
        description="Log files directory (relative to data_root)",
        json_schema_extra={
            "env_var": "PATH_LOGS",
            "category": "logs"
        }
    )
    temp_dir: str = Field(
        default="temp",
        description="Temporary files directory (relative to data_root)",
        json_schema_extra={
            "env_var": "PATH_TEMP",
            "effect": "Temporary files are periodically cleaned",
            "category": "temp"
        }
    )

    def get_absolute_path(self, dir_attr: str) -> Path:
        """
        상대 경로 속성을 절대 경로로 변환.

        Args:
            dir_attr: 속성명 (예: 'uploads_dir', 'summaries_dir')

        Returns:
            절대 경로 (Path 객체)

        Raises:
            AttributeError: 존재하지 않는 속성명인 경우
        """
        relative = getattr(self, dir_attr)
        return Path(self.data_root) / relative

    def ensure_directories(self) -> None:
        """
        모든 필요 디렉토리를 자동 생성.

        애플리케이션 시작 시 호출하여 필요한 디렉토리가
        존재하는지 확인하고 없으면 생성합니다.
        """
        dir_attrs = [
            'uploads_dir',
            'summaries_dir',
            'models_dir',
            'qlora_adapters_dir',
            'training_data_dir',
            'logs_dir',
            'temp_dir'
        ]
        for dir_attr in dir_attrs:
            path = self.get_absolute_path(dir_attr)
            path.mkdir(parents=True, exist_ok=True)

    def get_uploads_path(self) -> Path:
        """업로드 디렉토리 절대 경로"""
        return self.get_absolute_path('uploads_dir')

    def get_summaries_path(self) -> Path:
        """요약본 디렉토리 절대 경로"""
        return self.get_absolute_path('summaries_dir')

    def get_models_path(self) -> Path:
        """모델 디렉토리 절대 경로"""
        return self.get_absolute_path('models_dir')

    def get_logs_path(self) -> Path:
        """로그 디렉토리 절대 경로"""
        return self.get_absolute_path('logs_dir')

    model_config = {
        "json_schema_extra": {
            "description": "Centralized path configuration for file system operations"
        }
    }
