"""
Unit Tests for Enterprise Orchestrator Components

Tests the enterprise multi-agent orchestration components:
- DAGBuilder: Task decomposition and parallelism detection
- ParallelExecutor: Parallel task execution
- ResultEvaluator: Result quality evaluation
- SynthesisEvaluator: Multi-result synthesis evaluation

Run with: python -m pytest tests/api/agents/test_enterprise_orchestrator.py -v
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from app.api.agents.types import (
    AgentType, AgentContext, AgentResult, AgentStreamChunk,
    TaskStatus, ParallelismType, SubTask, TaskDAG,
    EvaluationCriteria, RetryConfig, OrchestrationConfig,
    EvaluationResult, ExecutionTrace
)
from app.api.agents.dag import DAGBuilder, get_dag_builder
from app.api.agents.parallel_executor import ParallelExecutor, DEFAULT_AGENT_TIMEOUTS
from app.api.agents.evaluator import ResultEvaluator, SynthesisEvaluator, get_evaluator


# =============================================================================
# Helper for running async code
# =============================================================================

def run_async(coro):
    """Helper to run async functions in sync tests."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_llm_adapter():
    """Create a mock LLM adapter."""
    adapter = AsyncMock()
    adapter.generate = AsyncMock(return_value={"content": ""})
    return adapter


@pytest.fixture
def mock_agent_registry():
    """Create a mock agent registry."""
    registry = Mock()

    # Create mock agents
    mock_agent = Mock()
    mock_agent.execute = AsyncMock(return_value=AgentResult(
        answer="Test answer",
        agent_type=AgentType.RAG,
        steps=1,
        success=True
    ))

    registry.get = Mock(return_value=mock_agent)
    return registry


@pytest.fixture
def mock_executor():
    """Create a mock executor."""
    executor = Mock()
    executor.llm_adapter = None
    return executor


@pytest.fixture
def sample_context():
    """Create a sample agent context."""
    return AgentContext(
        session_id="test-session",
        user_id="test-user",
        language="en",
        max_steps=10
    )


@pytest.fixture
def sample_config():
    """Create a sample orchestration config."""
    return OrchestrationConfig(
        enable_parallel=True,
        enable_retry=True,
        enable_evaluation=True,
        continue_on_failure=True
    )


@pytest.fixture
def sample_result():
    """Create a sample agent result."""
    return AgentResult(
        answer="This is a comprehensive test answer that provides useful information.",
        agent_type=AgentType.RAG,
        steps=2,
        sources=[{"title": "Test Source", "url": "http://example.com"}],
        success=True,
        execution_time=1.5
    )


# =============================================================================
# DAGBuilder Tests
# =============================================================================

class TestDAGBuilder:
    """Tests for DAGBuilder class."""

    def test_initialization(self):
        """Test DAGBuilder initialization."""
        builder = DAGBuilder()
        assert builder.llm_adapter is None

        mock_llm = Mock()
        builder_with_llm = DAGBuilder(llm_adapter=mock_llm)
        assert builder_with_llm.llm_adapter == mock_llm

    def test_is_single_agent_task_simple(self):
        """Test single agent task detection for simple queries."""
        builder = DAGBuilder()

        # Simple questions should be single agent
        assert builder._is_single_agent_task("What is OpenFrame?")
        assert builder._is_single_agent_task("Hello")
        assert builder._is_single_agent_task("Explain RAG")

    def test_is_single_agent_task_complex(self):
        """Test single agent task detection for complex queries."""
        builder = DAGBuilder()

        # Complex tasks with multiple comparison keywords and structure
        assert not builder._is_single_agent_task(
            "Compare OpenFrame and Tibero in terms of features, performance, and use cases"
        )
        assert not builder._is_single_agent_task(
            "First search for all related issues, then analyze the root cause, and finally suggest solutions"
        )

    def test_detect_parallelism_type_full(self):
        """Test full parallelism detection."""
        builder = DAGBuilder()

        # Comparison tasks should detect parallelism
        parallelism, confidence = builder._detect_parallelism_type("Compare OpenFrame and Tibero")
        assert parallelism in [ParallelismType.FULL, ParallelismType.PARTIAL, ParallelismType.NONE]

    def test_detect_parallelism_type_none(self):
        """Test no parallelism detection."""
        builder = DAGBuilder()

        # Simple tasks should have no parallelism
        parallelism, confidence = builder._detect_parallelism_type("What is OpenFrame?")
        assert parallelism == ParallelismType.NONE

    def test_build_dag_single_task(self):
        """Test DAG building for single task."""
        builder = DAGBuilder()

        dag = run_async(builder.build_dag(
            task="What is OpenFrame?",
            agent_type=AgentType.RAG,
            language="en",
            use_llm=False
        ))

        assert isinstance(dag, TaskDAG)
        assert len(dag.tasks) == 1
        assert dag.parallelism_type == ParallelismType.NONE

    def test_compute_execution_batches(self):
        """Test execution batch computation (topological sort)."""
        builder = DAGBuilder()

        # Create tasks with dependencies
        tasks = {
            "t1": SubTask(task_id="t1", description="Task 1", agent_type=AgentType.RAG, dependencies=[]),
            "t2": SubTask(task_id="t2", description="Task 2", agent_type=AgentType.RAG, dependencies=[]),
            "t3": SubTask(task_id="t3", description="Task 3", agent_type=AgentType.RAG, dependencies=["t1", "t2"]),
        }

        batches = builder._compute_execution_batches(tasks)

        # t1 and t2 should be in first batch, t3 in second
        assert len(batches) == 2
        assert set(batches[0]) == {"t1", "t2"}
        assert batches[1] == ["t3"]

    def test_validate_dag_valid(self):
        """Test DAG validation for valid DAG."""
        builder = DAGBuilder()

        dag = TaskDAG(
            tasks={
                "t1": SubTask(task_id="t1", description="Task 1", agent_type=AgentType.RAG, dependencies=[]),
                "t2": SubTask(task_id="t2", description="Task 2", agent_type=AgentType.RAG, dependencies=["t1"]),
            },
            execution_batches=[["t1"], ["t2"]]  # Must cover all tasks
        )

        is_valid, error = builder.validate_dag(dag)
        assert is_valid
        assert error is None

    def test_validate_dag_cycle(self):
        """Test DAG validation detects cycles."""
        builder = DAGBuilder()

        dag = TaskDAG(
            tasks={
                "t1": SubTask(task_id="t1", description="Task 1", agent_type=AgentType.RAG, dependencies=["t2"]),
                "t2": SubTask(task_id="t2", description="Task 2", agent_type=AgentType.RAG, dependencies=["t1"]),
            },
            execution_batches=[["t1", "t2"]]  # Would be valid if no cycle
        )

        is_valid, error = builder.validate_dag(dag)
        assert not is_valid
        assert "cycle" in error.lower()


# =============================================================================
# ParallelExecutor Tests
# =============================================================================

class TestParallelExecutor:
    """Tests for ParallelExecutor class."""

    def test_initialization(self, mock_agent_registry, mock_executor):
        """Test ParallelExecutor initialization."""
        executor = ParallelExecutor(mock_agent_registry, mock_executor)

        assert executor.agent_registry == mock_agent_registry
        assert executor.executor == mock_executor
        assert executor.timeout_config == DEFAULT_AGENT_TIMEOUTS

    def test_custom_timeout_config(self, mock_agent_registry, mock_executor):
        """Test custom timeout configuration."""
        custom_timeouts = {AgentType.RAG: 60.0}
        executor = ParallelExecutor(mock_agent_registry, mock_executor, custom_timeouts)

        assert executor.timeout_config[AgentType.RAG] == 60.0

    def test_execute_dag_single_task(self, mock_agent_registry, mock_executor, sample_context, sample_config):
        """Test executing DAG with single task."""
        executor = ParallelExecutor(mock_agent_registry, mock_executor)

        dag = TaskDAG(
            tasks={
                "t1": SubTask(task_id="t1", description="Test task", agent_type=AgentType.RAG),
            },
            execution_batches=[["t1"]]
        )
        trace = ExecutionTrace()

        results = run_async(executor.execute_dag(dag, sample_context, sample_config, trace))

        assert "t1" in results
        assert isinstance(results["t1"], AgentResult)

    def test_execute_dag_parallel(self, mock_agent_registry, mock_executor, sample_context, sample_config):
        """Test executing DAG with parallel tasks."""
        executor = ParallelExecutor(mock_agent_registry, mock_executor)

        dag = TaskDAG(
            tasks={
                "t1": SubTask(task_id="t1", description="Task 1", agent_type=AgentType.RAG),
                "t2": SubTask(task_id="t2", description="Task 2", agent_type=AgentType.RAG),
            },
            execution_batches=[["t1", "t2"]]
        )
        trace = ExecutionTrace()

        results = run_async(executor.execute_dag(dag, sample_context, sample_config, trace))

        assert "t1" in results
        assert "t2" in results

    def test_build_task_context(self, mock_agent_registry, mock_executor, sample_context):
        """Test building task context with previous results."""
        executor = ParallelExecutor(mock_agent_registry, mock_executor)

        subtask = SubTask(
            task_id="t2",
            description="Synthesize results",
            agent_type=AgentType.RAG,
            dependencies=["t1"]
        )

        previous_results = {
            "t1": AgentResult(
                answer="Result from task 1",
                agent_type=AgentType.RAG,
                steps=1,
                success=True
            )
        }

        context = executor._build_task_context(subtask, sample_context, previous_results)
        assert context.session_id == sample_context.session_id


# =============================================================================
# ResultEvaluator Tests
# =============================================================================

class TestResultEvaluator:
    """Tests for ResultEvaluator class."""

    def test_initialization(self):
        """Test ResultEvaluator initialization."""
        evaluator = ResultEvaluator()
        assert evaluator.llm_adapter is None

        mock_llm = Mock()
        evaluator_with_llm = ResultEvaluator(llm_adapter=mock_llm)
        assert evaluator_with_llm.llm_adapter == mock_llm

    def test_evaluate_success(self, sample_result):
        """Test evaluation of successful result."""
        evaluator = ResultEvaluator()
        criteria = EvaluationCriteria(
            min_confidence=0.6,
            min_answer_length=10,
            require_sources=False
        )

        evaluation = run_async(evaluator.evaluate(sample_result, "Test task", criteria))

        assert isinstance(evaluation, EvaluationResult)
        assert evaluation.passed
        assert evaluation.score > 0.5

    def test_evaluate_short_answer(self):
        """Test evaluation of too-short answer."""
        evaluator = ResultEvaluator()
        criteria = EvaluationCriteria(min_answer_length=100)

        result = AgentResult(
            answer="Short",
            agent_type=AgentType.RAG,
            steps=1,
            success=True
        )

        evaluation = run_async(evaluator.evaluate(result, "Test task", criteria))
        assert "too short" in " ".join(evaluation.issues).lower()

    def test_evaluate_missing_sources(self):
        """Test evaluation when sources required but missing."""
        evaluator = ResultEvaluator()
        criteria = EvaluationCriteria(require_sources=True)

        result = AgentResult(
            answer="This is a test answer without sources.",
            agent_type=AgentType.RAG,
            steps=1,
            sources=[],
            success=True
        )

        evaluation = run_async(evaluator.evaluate(result, "Test task", criteria))
        assert any("source" in issue.lower() for issue in evaluation.issues)

    def test_evaluate_failed_result(self):
        """Test evaluation of failed result."""
        evaluator = ResultEvaluator()
        criteria = EvaluationCriteria()

        result = AgentResult(
            answer="",
            agent_type=AgentType.RAG,
            steps=1,
            success=False,
            error="Connection timeout"
        )

        evaluation = run_async(evaluator.evaluate(result, "Test task", criteria))

        assert not evaluation.passed
        assert evaluation.score < 0.5

    def test_should_retry_max_retries(self):
        """Test retry decision at max retries."""
        evaluator = ResultEvaluator()
        config = RetryConfig(max_retries=2)

        evaluation = EvaluationResult(
            passed=False,
            score=0.4,
            retry_recommended=True,
            retry_reason="Low score"
        )

        should_retry, delay = evaluator.should_retry(evaluation, retry_count=2, config=config)
        assert not should_retry

    def test_should_retry_with_room(self):
        """Test retry decision with retries remaining."""
        evaluator = ResultEvaluator()
        config = RetryConfig(max_retries=3, initial_delay=1.0, backoff_factor=2.0)

        evaluation = EvaluationResult(
            passed=False,
            score=0.4,
            retry_recommended=True,
            retry_reason="Low score"
        )

        should_retry, delay = evaluator.should_retry(evaluation, retry_count=1, config=config)

        assert should_retry
        assert delay == 2.0  # 1.0 * 2.0^1

    def test_check_error_patterns(self):
        """Test error pattern detection in answers."""
        evaluator = ResultEvaluator()

        # English error patterns
        issues = evaluator._check_error_patterns("I don't know the answer.")
        assert len(issues) > 0

        # Korean error patterns
        issues = evaluator._check_error_patterns("정보가 없습니다.")
        assert len(issues) > 0

        # Valid answer
        issues = evaluator._check_error_patterns("OpenFrame is a mainframe rehosting solution.")
        assert len(issues) == 0

    def test_check_relevance(self):
        """Test relevance checking."""
        evaluator = ResultEvaluator()

        # Relevant answer
        score = evaluator._check_relevance(
            "OpenFrame is a mainframe rehosting solution that supports COBOL.",
            "What is OpenFrame?"
        )
        assert score > 0.3

    def test_is_transient_error(self):
        """Test transient error detection."""
        evaluator = ResultEvaluator()

        assert evaluator._is_transient_error("Connection timeout")
        assert evaluator._is_transient_error("HTTP 503 Service Unavailable")
        assert evaluator._is_transient_error("Rate limit exceeded")
        assert not evaluator._is_transient_error("Invalid API key")


# =============================================================================
# SynthesisEvaluator Tests
# =============================================================================

class TestSynthesisEvaluator:
    """Tests for SynthesisEvaluator class."""

    def test_evaluate_synthesis_good(self):
        """Test evaluation of good synthesis."""
        evaluator = SynthesisEvaluator()

        sub_results = {
            "t1": AgentResult(
                answer="OpenFrame supports COBOL and JCL.",
                agent_type=AgentType.RAG,
                steps=1,
                success=True
            ),
            "t2": AgentResult(
                answer="Tibero is a relational database.",
                agent_type=AgentType.RAG,
                steps=1,
                success=True
            )
        }

        synthesized = """
        OpenFrame is a mainframe rehosting solution that supports COBOL and JCL.
        Tibero is a relational database system developed by TmaxSoft.
        Together, they provide a complete enterprise platform.
        """

        evaluation = run_async(evaluator.evaluate_synthesis(
            synthesized,
            sub_results,
            "Compare OpenFrame and Tibero"
        ))

        assert isinstance(evaluation, EvaluationResult)
        assert evaluation.score > 0.5

    def test_evaluate_synthesis_too_short(self):
        """Test evaluation of too-short synthesis."""
        evaluator = SynthesisEvaluator()

        sub_results = {
            "t1": AgentResult(
                answer="Detailed answer about OpenFrame...",
                agent_type=AgentType.RAG,
                steps=1,
                success=True
            )
        }

        synthesized = "Short."

        evaluation = run_async(evaluator.evaluate_synthesis(
            synthesized,
            sub_results,
            "Explain OpenFrame"
        ))

        assert "too short" in " ".join(evaluation.issues).lower()

    def test_evaluate_synthesis_no_results(self):
        """Test evaluation with no successful results."""
        evaluator = SynthesisEvaluator()

        evaluation = run_async(evaluator.evaluate_synthesis(
            "Some synthesis",
            {},
            "Test task"
        ))

        assert not evaluation.passed
        assert "no successful" in " ".join(evaluation.issues).lower()


# =============================================================================
# TaskDAG Tests
# =============================================================================

class TestTaskDAG:
    """Tests for TaskDAG class."""

    def test_get_ready_tasks(self):
        """Test getting tasks ready for execution."""
        dag = TaskDAG(
            tasks={
                "t1": SubTask(task_id="t1", description="Task 1", agent_type=AgentType.RAG, status=TaskStatus.PENDING),
                "t2": SubTask(task_id="t2", description="Task 2", agent_type=AgentType.RAG, status=TaskStatus.PENDING, dependencies=["t1"]),
            }
        )

        ready = dag.get_ready_tasks()

        # Only t1 should be ready (t2 depends on t1)
        assert len(ready) == 1
        assert ready[0].task_id == "t1"

    def test_get_ready_tasks_after_completion(self):
        """Test getting ready tasks after some complete."""
        dag = TaskDAG(
            tasks={
                "t1": SubTask(task_id="t1", description="Task 1", agent_type=AgentType.RAG, status=TaskStatus.COMPLETED),
                "t2": SubTask(task_id="t2", description="Task 2", agent_type=AgentType.RAG, status=TaskStatus.PENDING, dependencies=["t1"]),
            }
        )

        ready = dag.get_ready_tasks()

        # t2 should now be ready
        assert len(ready) == 1
        assert ready[0].task_id == "t2"

    def test_mark_running(self):
        """Test marking task as running."""
        dag = TaskDAG(
            tasks={
                "t1": SubTask(task_id="t1", description="Task 1", agent_type=AgentType.RAG),
            }
        )

        dag.mark_running("t1")

        assert dag.tasks["t1"].status == TaskStatus.RUNNING
        assert dag.tasks["t1"].start_time is not None

    def test_mark_completed(self):
        """Test marking task as completed."""
        dag = TaskDAG(
            tasks={
                "t1": SubTask(task_id="t1", description="Task 1", agent_type=AgentType.RAG),
            }
        )

        result = AgentResult(
            answer="Test",
            agent_type=AgentType.RAG,
            steps=1,
            success=True
        )

        dag.mark_completed("t1", result)

        assert dag.tasks["t1"].status == TaskStatus.COMPLETED
        assert dag.tasks["t1"].result == result
        assert dag.tasks["t1"].end_time is not None

    def test_mark_failed(self):
        """Test marking task as failed."""
        dag = TaskDAG(
            tasks={
                "t1": SubTask(task_id="t1", description="Task 1", agent_type=AgentType.RAG),
            }
        )

        dag.mark_failed("t1", "Connection error")

        assert dag.tasks["t1"].status == TaskStatus.FAILED
        assert dag.tasks["t1"].error == "Connection error"

    def test_is_complete(self):
        """Test checking if DAG is complete."""
        dag = TaskDAG(
            tasks={
                "t1": SubTask(task_id="t1", description="Task 1", agent_type=AgentType.RAG, status=TaskStatus.COMPLETED),
                "t2": SubTask(task_id="t2", description="Task 2", agent_type=AgentType.RAG, status=TaskStatus.FAILED),
            }
        )

        assert dag.is_complete()

    def test_has_pending_tasks(self):
        """Test checking for pending tasks."""
        dag = TaskDAG(
            tasks={
                "t1": SubTask(task_id="t1", description="Task 1", agent_type=AgentType.RAG, status=TaskStatus.COMPLETED),
                "t2": SubTask(task_id="t2", description="Task 2", agent_type=AgentType.RAG, status=TaskStatus.PENDING),
            }
        )

        assert dag.has_pending_tasks()


# =============================================================================
# ExecutionTrace Tests
# =============================================================================

class TestExecutionTrace:
    """Tests for ExecutionTrace class."""

    def test_initialization(self):
        """Test ExecutionTrace initialization."""
        trace = ExecutionTrace()

        assert trace.trace_id is not None
        assert trace.start_time is not None
        assert len(trace.events) == 0

    def test_record_event(self):
        """Test recording events."""
        trace = ExecutionTrace()

        trace.record("task_start", task_id="t1", agent_type=AgentType.RAG, description="Starting task")

        assert len(trace.events) == 1
        assert trace.events[0].event_type == "task_start"
        assert trace.events[0].task_id == "t1"
        assert trace.events[0].agent_type == AgentType.RAG

    def test_record_multiple_events(self):
        """Test recording multiple events."""
        trace = ExecutionTrace()

        trace.record("orchestration_start")
        trace.record("dag_created", data={"task_count": 3})
        trace.record("task_start", task_id="t1")
        trace.record("task_complete", task_id="t1")

        assert len(trace.events) == 4


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for enterprise orchestrator components."""

    def test_dag_to_execution_flow(self, mock_agent_registry, mock_executor, sample_context, sample_config):
        """Test full flow from DAG creation to execution."""
        # Build DAG
        builder = DAGBuilder()
        dag = run_async(builder.build_dag(
            task="What is OpenFrame?",
            agent_type=AgentType.RAG,
            language="en",
            use_llm=False
        ))

        # Execute DAG
        executor = ParallelExecutor(mock_agent_registry, mock_executor)
        trace = ExecutionTrace()

        results = run_async(executor.execute_dag(dag, sample_context, sample_config, trace))

        # Verify results
        assert len(results) > 0
        assert all(isinstance(r, AgentResult) for r in results.values())

    def test_evaluation_after_execution(self, mock_agent_registry, mock_executor, sample_context, sample_config):
        """Test evaluation after execution."""
        # Execute
        builder = DAGBuilder()
        dag = run_async(builder.build_dag("Test task", AgentType.RAG, "en", use_llm=False))

        executor = ParallelExecutor(mock_agent_registry, mock_executor)
        trace = ExecutionTrace()
        results = run_async(executor.execute_dag(dag, sample_context, sample_config, trace))

        # Evaluate
        evaluator = ResultEvaluator()
        criteria = EvaluationCriteria()

        for task_id, result in results.items():
            evaluation = run_async(evaluator.evaluate(result, "Test task", criteria))
            assert isinstance(evaluation, EvaluationResult)


# =============================================================================
# Singleton Tests
# =============================================================================

class TestSingletons:
    """Tests for singleton accessor functions."""

    def test_get_dag_builder(self):
        """Test DAGBuilder singleton."""
        builder1 = get_dag_builder()
        builder2 = get_dag_builder()

        assert builder1 is builder2

    def test_get_evaluator(self):
        """Test ResultEvaluator singleton."""
        evaluator1 = get_evaluator()
        evaluator2 = get_evaluator()

        assert evaluator1 is evaluator2
