"""Custom exceptions for the Legacy Modernization platform."""


class LegacyModernizationError(Exception):
    """Base exception for all legacy modernization errors."""


class WorkspaceNotFoundError(LegacyModernizationError):
    """Raised when a workspace is not found in the state store."""

    def __init__(self, asset_id: str):
        self.asset_id = asset_id
        super().__init__(f"Workspace not found: {asset_id}")


class PermissionDeniedError(LegacyModernizationError):
    """Raised when an agent attempts to write to a field it doesn't own."""

    def __init__(self, agent_role: str, field: str):
        self.agent_role = agent_role
        self.field = field
        super().__init__(
            f"Agent '{agent_role}' has no write permission for field '{field}'"
        )


class PipelineBlockedError(LegacyModernizationError):
    """Raised when the pipeline is blocked by a QA VETO."""

    def __init__(self, asset_id: str, reason: str):
        self.asset_id = asset_id
        self.reason = reason
        super().__init__(f"Pipeline blocked for {asset_id}: {reason}")


class MaxReanalysisExceededError(LegacyModernizationError):
    """Raised when reanalysis iteration limit is reached."""

    def __init__(self, asset_id: str, max_iterations: int):
        self.asset_id = asset_id
        self.max_iterations = max_iterations
        super().__init__(
            f"Max reanalysis iterations ({max_iterations}) exceeded for {asset_id}"
        )


class ParserError(LegacyModernizationError):
    """Raised when a parser encounters an unrecoverable error."""

    def __init__(self, parser_type: str, file_path: str, detail: str):
        self.parser_type = parser_type
        self.file_path = file_path
        self.detail = detail
        super().__init__(f"{parser_type} parser error in {file_path}: {detail}")


class EventBusError(LegacyModernizationError):
    """Raised when the event bus encounters a communication error."""


class PluginLoadError(LegacyModernizationError):
    """Raised when a plugin fails to load or validate."""

    def __init__(self, plugin_name: str, reason: str):
        self.plugin_name = plugin_name
        self.reason = reason
        super().__init__(f"Failed to load plugin '{plugin_name}': {reason}")
