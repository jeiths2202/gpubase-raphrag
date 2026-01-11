"""
Base Use Case
Abstract base class for all use cases.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TypeVar, Generic, Optional, Dict, Any, List
from datetime import datetime, timezone
from enum import Enum
import uuid
import logging

logger = logging.getLogger(__name__)

# Input/Output type variables
TInput = TypeVar('TInput')
TOutput = TypeVar('TOutput')


class UseCaseStatus(str, Enum):
    """Use case execution status"""
    SUCCESS = "success"
    FAILURE = "failure"
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    UNAUTHORIZED = "unauthorized"
    RATE_LIMITED = "rate_limited"


@dataclass
class UseCaseResult(Generic[TOutput]):
    """
    Result of use case execution.

    Encapsulates success/failure state along with the result data
    or error information.
    """
    status: UseCaseStatus
    data: Optional[TOutput] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    errors: List[Dict[str, Any]] = field(default_factory=list)

    # Execution metadata
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    execution_time_ms: int = 0
    timestamp: datetime = field(default_factory=datetime.now(timezone.utc))

    @property
    def is_success(self) -> bool:
        return self.status == UseCaseStatus.SUCCESS

    @property
    def is_failure(self) -> bool:
        return self.status != UseCaseStatus.SUCCESS

    @classmethod
    def success(cls, data: TOutput, execution_time_ms: int = 0) -> "UseCaseResult[TOutput]":
        """Create successful result"""
        return cls(
            status=UseCaseStatus.SUCCESS,
            data=data,
            execution_time_ms=execution_time_ms
        )

    @classmethod
    def failure(
        cls,
        message: str,
        code: Optional[str] = None,
        status: UseCaseStatus = UseCaseStatus.FAILURE
    ) -> "UseCaseResult[TOutput]":
        """Create failure result"""
        return cls(
            status=status,
            error_message=message,
            error_code=code
        )

    @classmethod
    def validation_error(cls, errors: List[Dict[str, Any]]) -> "UseCaseResult[TOutput]":
        """Create validation error result"""
        return cls(
            status=UseCaseStatus.VALIDATION_ERROR,
            error_message="Validation failed",
            errors=errors
        )

    @classmethod
    def not_found(cls, resource: str, resource_id: str) -> "UseCaseResult[TOutput]":
        """Create not found result"""
        return cls(
            status=UseCaseStatus.NOT_FOUND,
            error_message=f"{resource} '{resource_id}' not found",
            error_code="NOT_FOUND"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = {
            "status": self.status.value,
            "execution_id": self.execution_id,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp.isoformat()
        }

        if self.is_success and self.data:
            if hasattr(self.data, 'to_dict'):
                result["data"] = self.data.to_dict()
            else:
                result["data"] = self.data

        if self.is_failure:
            result["error"] = {
                "message": self.error_message,
                "code": self.error_code,
                "errors": self.errors
            }

        return result


@dataclass
class UseCaseContext:
    """
    Context for use case execution.

    Contains user information and request metadata.
    """
    user_id: str
    user_email: Optional[str] = None
    user_role: str = "user"

    # Request context
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None
    ip_address: Optional[str] = None

    # Feature flags
    features: Dict[str, bool] = field(default_factory=dict)

    def has_feature(self, feature: str) -> bool:
        return self.features.get(feature, False)

    def is_admin(self) -> bool:
        return self.user_role in ("admin", "super_admin")


class UseCase(ABC, Generic[TInput, TOutput]):
    """
    Abstract base class for use cases.

    Use cases represent a single, focused business operation.
    They orchestrate entities, repositories, and external services
    to accomplish a specific goal.

    Design principles:
    1. Single Responsibility: One use case = one business operation
    2. Input/Output: Clearly defined input and output types
    3. No Side Effects: Same input always produces same output
    4. Testable: All dependencies injected through constructor

    Example:
        class CreateOrderUseCase(UseCase[CreateOrderInput, Order]):
            def __init__(
                self,
                order_repo: OrderRepository,
                payment_service: PaymentPort,
                notification_service: NotificationPort
            ):
                self.order_repo = order_repo
                self.payment = payment_service
                self.notification = notification_service

            async def execute(
                self,
                input: CreateOrderInput,
                context: UseCaseContext
            ) -> UseCaseResult[Order]:
                # Validate
                if not self._validate(input):
                    return UseCaseResult.validation_error(...)

                # Execute business logic
                order = Order.create(input)
                await self.order_repo.save(order)
                await self.payment.charge(order)
                await self.notification.send(order)

                return UseCaseResult.success(order)
    """

    @abstractmethod
    async def execute(
        self,
        input: TInput,
        context: UseCaseContext
    ) -> UseCaseResult[TOutput]:
        """
        Execute the use case.

        Args:
            input: Use case input data
            context: Execution context (user, request info)

        Returns:
            UseCaseResult with output data or error
        """
        pass

    def _log_execution(
        self,
        input: TInput,
        context: UseCaseContext,
        result: UseCaseResult[TOutput]
    ) -> None:
        """Log use case execution"""
        use_case_name = self.__class__.__name__

        if result.is_success:
            logger.info(
                f"{use_case_name} executed successfully",
                extra={
                    "use_case": use_case_name,
                    "user_id": context.user_id,
                    "execution_id": result.execution_id,
                    "execution_time_ms": result.execution_time_ms
                }
            )
        else:
            logger.warning(
                f"{use_case_name} failed: {result.error_message}",
                extra={
                    "use_case": use_case_name,
                    "user_id": context.user_id,
                    "execution_id": result.execution_id,
                    "error_code": result.error_code
                }
            )


class TransactionalUseCase(UseCase[TInput, TOutput], ABC):
    """
    Use case with transaction support.

    Automatically handles transaction begin/commit/rollback.
    """

    async def execute(
        self,
        input: TInput,
        context: UseCaseContext
    ) -> UseCaseResult[TOutput]:
        """Execute with transaction wrapper"""
        try:
            await self._begin_transaction()
            result = await self._execute_impl(input, context)

            if result.is_success:
                await self._commit()
            else:
                await self._rollback()

            return result

        except Exception as e:
            await self._rollback()
            logger.exception(f"Transaction failed: {e}")
            return UseCaseResult.failure(str(e))

    @abstractmethod
    async def _execute_impl(
        self,
        input: TInput,
        context: UseCaseContext
    ) -> UseCaseResult[TOutput]:
        """Actual use case implementation"""
        pass

    async def _begin_transaction(self) -> None:
        """Begin transaction - override if needed"""
        pass

    async def _commit(self) -> None:
        """Commit transaction - override if needed"""
        pass

    async def _rollback(self) -> None:
        """Rollback transaction - override if needed"""
        pass
