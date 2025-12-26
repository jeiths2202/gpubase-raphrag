"""
Application Mode Configuration
Supports Develop and Product modes with different logging behaviors
"""
import os
import yaml
import argparse
from enum import Enum
from typing import Optional, Dict, Any
from functools import lru_cache
from dataclasses import dataclass, field
from pathlib import Path


class AppMode(str, Enum):
    """Application running modes"""
    DEVELOP = "develop"
    PRODUCT = "product"

    @classmethod
    def from_string(cls, value: str) -> "AppMode":
        """Parse mode from string"""
        value = value.lower().strip()
        if value in ("develop", "dev", "development", "debug"):
            return cls.DEVELOP
        elif value in ("product", "prod", "production"):
            return cls.PRODUCT
        else:
            raise ValueError(f"Unknown app mode: {value}. Use 'develop' or 'product'")


@dataclass
class ModeConfig:
    """Configuration settings per mode"""
    # Logging
    log_level: str = "INFO"
    enable_token_logging: bool = False
    enable_stack_trace: bool = False
    enable_debug_logs: bool = False
    log_sampling_rate: float = 1.0  # 1.0 = log all, 0.1 = log 10%

    # Performance
    enable_performance_tracking: bool = False
    slow_request_threshold_ms: int = 1000

    # Error handling
    expose_internal_errors: bool = False

    # APM/Telemetry
    enable_tracing: bool = False
    trace_sampling_rate: float = 1.0


# Default configurations per mode
DEVELOP_CONFIG = ModeConfig(
    log_level="DEBUG",
    enable_token_logging=True,
    enable_stack_trace=True,
    enable_debug_logs=True,
    log_sampling_rate=1.0,
    enable_performance_tracking=True,
    slow_request_threshold_ms=500,
    expose_internal_errors=True,
    enable_tracing=True,
    trace_sampling_rate=1.0
)

PRODUCT_CONFIG = ModeConfig(
    log_level="INFO",
    enable_token_logging=False,
    enable_stack_trace=False,
    enable_debug_logs=False,
    log_sampling_rate=0.1,  # Only log 10% in production
    enable_performance_tracking=True,
    slow_request_threshold_ms=2000,
    expose_internal_errors=False,
    enable_tracing=True,
    trace_sampling_rate=0.1
)


class AppModeManager:
    """
    Centralized application mode manager.
    Supports configuration from:
    1. Environment variable (APP_MODE)
    2. Config file (config.yaml)
    3. CLI arguments
    """

    _instance: Optional["AppModeManager"] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._mode: AppMode = AppMode.PRODUCT  # Default to product for safety
        self._config: ModeConfig = PRODUCT_CONFIG
        self._custom_config: Dict[str, Any] = {}
        self._initialized = True

        # Auto-initialize from available sources
        self._load_configuration()

    def _load_configuration(self):
        """Load configuration from multiple sources with priority"""
        mode = None

        # Priority 1: Environment variable
        env_mode = os.environ.get("APP_MODE")
        if env_mode:
            try:
                mode = AppMode.from_string(env_mode)
            except ValueError:
                pass

        # Priority 2: Config file (can override env if explicitly set)
        config_paths = [
            Path("config.yaml"),
            Path("config/config.yaml"),
            Path("app/config.yaml"),
            Path(os.environ.get("CONFIG_FILE", ""))
        ]

        for config_path in config_paths:
            if config_path.exists():
                try:
                    with open(config_path) as f:
                        yaml_config = yaml.safe_load(f)
                        if yaml_config and "app_mode" in yaml_config:
                            mode = AppMode.from_string(yaml_config["app_mode"])
                            self._custom_config = yaml_config.get("mode_config", {})
                            break
                except Exception:
                    pass

        # Apply mode
        if mode:
            self.set_mode(mode)

    def parse_cli_args(self) -> AppMode:
        """Parse CLI arguments for mode selection"""
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument(
            "--mode", "-m",
            type=str,
            choices=["develop", "product", "dev", "prod"],
            default=None,
            help="Application mode (develop/product)"
        )

        args, _ = parser.parse_known_args()

        if args.mode:
            mode = AppMode.from_string(args.mode)
            self.set_mode(mode)
            return mode

        return self._mode

    def set_mode(self, mode: AppMode):
        """Set application mode and update configuration"""
        self._mode = mode

        if mode == AppMode.DEVELOP:
            self._config = ModeConfig(**{
                **DEVELOP_CONFIG.__dict__,
                **self._custom_config
            })
        else:
            self._config = ModeConfig(**{
                **PRODUCT_CONFIG.__dict__,
                **self._custom_config
            })

    @property
    def mode(self) -> AppMode:
        """Get current mode"""
        return self._mode

    @property
    def config(self) -> ModeConfig:
        """Get current mode configuration"""
        return self._config

    @property
    def is_develop(self) -> bool:
        """Check if running in develop mode"""
        return self._mode == AppMode.DEVELOP

    @property
    def is_product(self) -> bool:
        """Check if running in product mode"""
        return self._mode == AppMode.PRODUCT

    def get_log_level(self) -> str:
        """Get appropriate log level for current mode"""
        return self._config.log_level

    def should_log_tokens(self) -> bool:
        """Check if token-level logging is enabled"""
        return self._config.enable_token_logging

    def should_log_stack_trace(self) -> bool:
        """Check if stack traces should be logged"""
        return self._config.enable_stack_trace

    def should_expose_internal_errors(self) -> bool:
        """Check if internal errors should be exposed"""
        return self._config.expose_internal_errors


@lru_cache()
def get_app_mode_manager() -> AppModeManager:
    """Get singleton AppModeManager instance"""
    return AppModeManager()


# Convenience functions
def get_current_mode() -> AppMode:
    """Get current application mode"""
    return get_app_mode_manager().mode


def is_develop_mode() -> bool:
    """Check if in develop mode"""
    return get_app_mode_manager().is_develop


def is_product_mode() -> bool:
    """Check if in product mode"""
    return get_app_mode_manager().is_product


def get_mode_config() -> ModeConfig:
    """Get current mode configuration"""
    return get_app_mode_manager().config
