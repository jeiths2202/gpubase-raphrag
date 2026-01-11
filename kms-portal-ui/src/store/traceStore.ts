/**
 * Trace Store
 *
 * Zustand store for agent execution trace visualization.
 * Manages real-time trace data and panel state.
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

// ============================================================================
// Types
// ============================================================================

export type SpanStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'skipped';

export interface DAGTask {
  task_id: string;
  description: string;
  agent_type: string;
  status: SpanStatus;
  dependencies: string[];
  start_time?: string;
  end_time?: string;
  latency_ms?: number;
  error?: string;
}

export interface DAGStructure {
  tasks: DAGTask[];
  execution_batches: string[][];
  parallelism_type: string;
}

export interface TimelineEvent {
  event: string;
  task_id?: string;
  agent_type?: string;
  timestamp: string;
  success?: boolean;
  latency_ms?: number;
  error?: string;
  data?: Record<string, unknown>;
}

export interface EvaluationResult {
  passed: boolean;
  score?: number;
  issues: string[];
  retry_recommended?: boolean;
  retry_reason?: string;
}

export interface CurrentTask {
  task_id: string;
  status: SpanStatus;
  start_time?: string;
  end_time?: string;
  latency_ms?: number;
  error?: string;
}

export interface TraceData {
  traceId: string | null;
  dag: DAGStructure | null;
  currentTask: CurrentTask | null;
  timeline: TimelineEvent[];
  evaluations: Record<string, EvaluationResult>;
}

export type ViewMode = 'dag' | 'timeline' | 'details';

export interface TracePanelState {
  isOpen: boolean;
  width: number;
  viewMode: ViewMode;
}

// ============================================================================
// Store Interface
// ============================================================================

interface TraceState {
  // Panel state (persisted)
  panel: TracePanelState;

  // Current trace data (not persisted)
  currentTrace: TraceData;

  // Panel actions
  openPanel: () => void;
  closePanel: () => void;
  togglePanel: () => void;
  setPanelWidth: (width: number) => void;
  setViewMode: (mode: ViewMode) => void;

  // Trace data actions
  initTrace: (traceId: string) => void;
  setDAG: (dag: DAGStructure) => void;
  updateTaskStatus: (taskId: string, status: SpanStatus, data?: Partial<DAGTask>) => void;
  addTimelineEvent: (event: TimelineEvent) => void;
  addEvaluation: (taskId: string, evaluation: EvaluationResult) => void;
  setCurrentTask: (task: CurrentTask | null) => void;
  clearTrace: () => void;

  // Bulk update from trace_data in SSE chunk
  updateFromTraceData: (traceData: {
    trace_id?: string;
    dag?: DAGStructure;
    current_task?: CurrentTask;
    timeline_event?: TimelineEvent;
    evaluations?: Record<string, EvaluationResult>;
  }) => void;
}

// ============================================================================
// Initial State
// ============================================================================

const initialTraceData: TraceData = {
  traceId: null,
  dag: null,
  currentTask: null,
  timeline: [],
  evaluations: {},
};

// ============================================================================
// Store
// ============================================================================

export const useTraceStore = create<TraceState>()(
  persist(
    (set, get) => ({
      // Initial state
      panel: {
        isOpen: false,
        width: 450,
        viewMode: 'dag' as ViewMode,
      },
      currentTrace: { ...initialTraceData },

      // Panel actions
      openPanel: () => set((state) => ({
        panel: { ...state.panel, isOpen: true }
      })),

      closePanel: () => set((state) => ({
        panel: { ...state.panel, isOpen: false }
      })),

      togglePanel: () => set((state) => ({
        panel: { ...state.panel, isOpen: !state.panel.isOpen }
      })),

      setPanelWidth: (width: number) => set((state) => ({
        panel: { ...state.panel, width: Math.min(Math.max(width, 300), 800) }
      })),

      setViewMode: (mode: ViewMode) => set((state) => ({
        panel: { ...state.panel, viewMode: mode }
      })),

      // Trace data actions
      initTrace: (traceId: string) => set({
        currentTrace: {
          ...initialTraceData,
          traceId,
        }
      }),

      setDAG: (dag: DAGStructure) => set((state) => ({
        currentTrace: {
          ...state.currentTrace,
          dag,
        }
      })),

      updateTaskStatus: (taskId: string, status: SpanStatus, data?: Partial<DAGTask>) => set((state) => {
        if (!state.currentTrace.dag) return state;

        const updatedTasks = state.currentTrace.dag.tasks.map((task) =>
          task.task_id === taskId
            ? { ...task, status, ...data }
            : task
        );

        return {
          currentTrace: {
            ...state.currentTrace,
            dag: {
              ...state.currentTrace.dag,
              tasks: updatedTasks,
            },
          },
        };
      }),

      addTimelineEvent: (event: TimelineEvent) => set((state) => ({
        currentTrace: {
          ...state.currentTrace,
          timeline: [...state.currentTrace.timeline, event],
        }
      })),

      addEvaluation: (taskId: string, evaluation: EvaluationResult) => set((state) => ({
        currentTrace: {
          ...state.currentTrace,
          evaluations: {
            ...state.currentTrace.evaluations,
            [taskId]: evaluation,
          },
        }
      })),

      setCurrentTask: (task: CurrentTask | null) => set((state) => ({
        currentTrace: {
          ...state.currentTrace,
          currentTask: task,
        }
      })),

      clearTrace: () => set({
        currentTrace: { ...initialTraceData }
      }),

      // Bulk update from SSE trace_data
      updateFromTraceData: (traceData) => {
        const state = get();
        const updates: Partial<TraceData> = {};

        // Update trace ID
        if (traceData.trace_id && !state.currentTrace.traceId) {
          updates.traceId = traceData.trace_id;
        }

        // Update DAG structure
        if (traceData.dag) {
          updates.dag = traceData.dag;
        }

        // Update current task
        if (traceData.current_task) {
          updates.currentTask = traceData.current_task;

          // Also update the task status in DAG
          if (state.currentTrace.dag) {
            const taskId = traceData.current_task.task_id;
            const status = traceData.current_task.status;
            const updatedTasks = state.currentTrace.dag.tasks.map((task) =>
              task.task_id === taskId
                ? {
                    ...task,
                    status,
                    start_time: traceData.current_task?.start_time || task.start_time,
                    end_time: traceData.current_task?.end_time || task.end_time,
                    latency_ms: traceData.current_task?.latency_ms || task.latency_ms,
                    error: traceData.current_task?.error || task.error,
                  }
                : task
            );
            updates.dag = {
              ...state.currentTrace.dag,
              tasks: updatedTasks,
            };
          }
        }

        // Add timeline event
        if (traceData.timeline_event) {
          updates.timeline = [
            ...state.currentTrace.timeline,
            traceData.timeline_event,
          ];
        }

        // Merge evaluations
        if (traceData.evaluations) {
          updates.evaluations = {
            ...state.currentTrace.evaluations,
            ...traceData.evaluations,
          };
        }

        if (Object.keys(updates).length > 0) {
          set({
            currentTrace: {
              ...state.currentTrace,
              ...updates,
            }
          });
        }
      },
    }),
    {
      name: 'trace-panel-storage',
      // Only persist panel state, not trace data
      partialize: (state) => ({
        panel: state.panel,
      }),
    }
  )
);

// ============================================================================
// Selectors
// ============================================================================

export const selectTracePanelOpen = (state: TraceState) => state.panel.isOpen;
export const selectTracePanelWidth = (state: TraceState) => state.panel.width;
export const selectViewMode = (state: TraceState) => state.panel.viewMode;
export const selectCurrentTrace = (state: TraceState) => state.currentTrace;
export const selectDAG = (state: TraceState) => state.currentTrace.dag;
export const selectTimeline = (state: TraceState) => state.currentTrace.timeline;
export const selectEvaluations = (state: TraceState) => state.currentTrace.evaluations;

// ============================================================================
// Helper to check if trace is active
// ============================================================================

export const isTraceActive = (state: TraceState): boolean => {
  const { dag } = state.currentTrace;
  if (!dag) return false;

  // Check if any task is still running
  return dag.tasks.some((task) => task.status === 'running' || task.status === 'pending');
};

export default useTraceStore;
