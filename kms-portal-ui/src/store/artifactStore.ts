/**
 * Artifact Store
 *
 * Manages artifact state for the AI Agent chat.
 * Features:
 * - Per-agent-type artifact collection
 * - Artifact collection and display
 * - Panel state management (open/close, resize)
 * - Selected artifact tracking
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { ArtifactType, ArtifactLanguage, AgentType } from '../api/agent.api';

// =============================================================================
// Types
// =============================================================================

/**
 * Artifact data structure
 */
export interface Artifact {
  id: string;
  type: ArtifactType;
  title: string;
  content: string;
  language?: ArtifactLanguage;
  lineCount: number;
  charCount: number;
  messageId?: string;
  agentType?: AgentType;
  createdAt: Date;
}

/**
 * Panel state
 */
export interface ArtifactPanelState {
  isOpen: boolean;
  width: number; // Panel width in pixels
  selectedArtifactId: string | null;
}

/**
 * Per-agent artifact state
 */
interface AgentArtifactState {
  artifacts: Artifact[];
  selectedArtifactId: string | null;
}

/**
 * Store state
 */
interface ArtifactState {
  // Per-agent artifacts
  agentArtifacts: Record<AgentType, AgentArtifactState>;

  // Panel state (shared across agents)
  panel: ArtifactPanelState;

  // Current agent type (for panel display)
  currentAgentType: AgentType;

  // Actions - Agent-specific Artifacts
  addArtifact: (agentType: AgentType, artifact: Artifact) => void;
  removeArtifact: (agentType: AgentType, id: string) => void;
  clearArtifacts: (agentType: AgentType) => void;
  updateArtifact: (agentType: AgentType, id: string, updates: Partial<Artifact>) => void;

  // Actions - Agent switching
  setCurrentAgentType: (agentType: AgentType) => void;

  // Actions - Panel
  openPanel: (artifactId?: string) => void;
  closePanel: () => void;
  togglePanel: () => void;
  setPanelWidth: (width: number) => void;
  selectArtifact: (id: string) => void;

  // Getters
  getArtifacts: (agentType: AgentType) => Artifact[];
  getArtifact: (agentType: AgentType, id: string) => Artifact | undefined;
  getSelectedArtifact: () => Artifact | undefined;
  getCurrentArtifacts: () => Artifact[];
}

// =============================================================================
// Constants
// =============================================================================

const MIN_PANEL_WIDTH = 300;
const MAX_PANEL_WIDTH = 1200;
const DEFAULT_PANEL_WIDTH = 500;

const createInitialAgentArtifactState = (): AgentArtifactState => ({
  artifacts: [],
  selectedArtifactId: null,
});

const initialAgentArtifacts: Record<AgentType, AgentArtifactState> = {
  auto: createInitialAgentArtifactState(),
  rag: createInitialAgentArtifactState(),
  ims: createInitialAgentArtifactState(),
  vision: createInitialAgentArtifactState(),
  code: createInitialAgentArtifactState(),
  planner: createInitialAgentArtifactState(),
};

// =============================================================================
// Store
// =============================================================================

export const useArtifactStore = create<ArtifactState>()(
  persist(
    (set, get) => ({
      // Initial state
      agentArtifacts: initialAgentArtifacts,
      panel: {
        isOpen: false,
        width: DEFAULT_PANEL_WIDTH,
        selectedArtifactId: null,
      },
      currentAgentType: 'auto',

      // Agent-specific artifact actions
      addArtifact: (agentType: AgentType, artifact: Artifact) => {
        set((state) => {
          const agentState = state.agentArtifacts[agentType];
          // Check if artifact with same ID already exists
          const exists = agentState.artifacts.some((a) => a.id === artifact.id);
          if (exists) {
            return state;
          }

          // Add agent type to artifact
          const artifactWithAgent = { ...artifact, agentType };

          return {
            agentArtifacts: {
              ...state.agentArtifacts,
              [agentType]: {
                ...agentState,
                artifacts: [...agentState.artifacts, artifactWithAgent],
                selectedArtifactId: artifact.id,
              },
            },
            // Auto-open panel if this is the current agent
            panel: state.currentAgentType === agentType
              ? {
                  ...state.panel,
                  isOpen: true,
                  selectedArtifactId: artifact.id,
                }
              : state.panel,
          };
        });
      },

      removeArtifact: (agentType: AgentType, id: string) => {
        set((state) => {
          const agentState = state.agentArtifacts[agentType];
          const newArtifacts = agentState.artifacts.filter((a) => a.id !== id);
          const wasSelected = agentState.selectedArtifactId === id;

          return {
            agentArtifacts: {
              ...state.agentArtifacts,
              [agentType]: {
                ...agentState,
                artifacts: newArtifacts,
                selectedArtifactId: wasSelected
                  ? newArtifacts[newArtifacts.length - 1]?.id || null
                  : agentState.selectedArtifactId,
              },
            },
            panel: state.currentAgentType === agentType && wasSelected
              ? {
                  ...state.panel,
                  selectedArtifactId: newArtifacts[newArtifacts.length - 1]?.id || null,
                }
              : state.panel,
          };
        });
      },

      clearArtifacts: (agentType: AgentType) => {
        set((state) => ({
          agentArtifacts: {
            ...state.agentArtifacts,
            [agentType]: {
              artifacts: [],
              selectedArtifactId: null,
            },
          },
          panel: state.currentAgentType === agentType
            ? {
                ...state.panel,
                isOpen: false,
                selectedArtifactId: null,
              }
            : state.panel,
        }));
      },

      updateArtifact: (agentType: AgentType, id: string, updates: Partial<Artifact>) => {
        set((state) => ({
          agentArtifacts: {
            ...state.agentArtifacts,
            [agentType]: {
              ...state.agentArtifacts[agentType],
              artifacts: state.agentArtifacts[agentType].artifacts.map((a) =>
                a.id === id ? { ...a, ...updates } : a
              ),
            },
          },
        }));
      },

      // Agent switching
      setCurrentAgentType: (agentType: AgentType) => {
        set((state) => {
          const agentState = state.agentArtifacts[agentType];
          return {
            currentAgentType: agentType,
            panel: {
              ...state.panel,
              // Update selected artifact to the current agent's selection
              selectedArtifactId: agentState.selectedArtifactId,
              // Close panel if switching agent has no artifacts
              isOpen: agentState.artifacts.length > 0 ? state.panel.isOpen : false,
            },
          };
        });
      },

      // Panel actions
      openPanel: (artifactId?: string) => {
        const state = get();
        const currentArtifacts = state.agentArtifacts[state.currentAgentType].artifacts;
        set({
          panel: {
            ...state.panel,
            isOpen: true,
            selectedArtifactId:
              artifactId ||
              state.panel.selectedArtifactId ||
              currentArtifacts[currentArtifacts.length - 1]?.id ||
              null,
          },
        });
      },

      closePanel: () => {
        set((state) => ({
          panel: {
            ...state.panel,
            isOpen: false,
          },
        }));
      },

      togglePanel: () => {
        set((state) => ({
          panel: {
            ...state.panel,
            isOpen: !state.panel.isOpen,
          },
        }));
      },

      setPanelWidth: (width: number) => {
        // Clamp width to valid range
        const clampedWidth = Math.max(
          MIN_PANEL_WIDTH,
          Math.min(MAX_PANEL_WIDTH, width)
        );
        set((state) => ({
          panel: {
            ...state.panel,
            width: clampedWidth,
          },
        }));
      },

      selectArtifact: (id: string) => {
        set((state) => {
          // Also update the agent's selected artifact
          const currentAgentState = state.agentArtifacts[state.currentAgentType];
          return {
            agentArtifacts: {
              ...state.agentArtifacts,
              [state.currentAgentType]: {
                ...currentAgentState,
                selectedArtifactId: id,
              },
            },
            panel: {
              ...state.panel,
              selectedArtifactId: id,
              isOpen: true,
            },
          };
        });
      },

      // Getters
      getArtifacts: (agentType: AgentType) => {
        return get().agentArtifacts[agentType].artifacts;
      },

      getArtifact: (agentType: AgentType, id: string) => {
        return get().agentArtifacts[agentType].artifacts.find((a) => a.id === id);
      },

      getSelectedArtifact: () => {
        const state = get();
        const currentArtifacts = state.agentArtifacts[state.currentAgentType].artifacts;
        if (!state.panel.selectedArtifactId) return undefined;
        return currentArtifacts.find(
          (a) => a.id === state.panel.selectedArtifactId
        );
      },

      getCurrentArtifacts: () => {
        const state = get();
        return state.agentArtifacts[state.currentAgentType].artifacts;
      },
    }),
    {
      name: 'artifact-storage',
      storage: createJSONStorage(() => localStorage),
      // Only persist panel width (not artifacts or selection)
      partialize: (state) => ({
        panel: {
          width: state.panel.width,
        },
      }),
    }
  )
);

// =============================================================================
// Selectors for use in components
// =============================================================================

/**
 * Get artifacts for the current agent (reactive)
 */
export const useCurrentArtifacts = () => {
  return useArtifactStore((state) =>
    state.agentArtifacts[state.currentAgentType].artifacts
  );
};

// =============================================================================
// Helper functions
// =============================================================================

/**
 * Create an Artifact from streaming chunk data
 */
export function createArtifactFromChunk(chunk: {
  artifact_id?: string;
  artifact_type?: ArtifactType;
  artifact_title?: string;
  artifact_language?: ArtifactLanguage;
  content?: string | null;
  metadata?: Record<string, unknown> | null;
  messageId?: string;
}): Artifact | null {
  if (!chunk.artifact_id || !chunk.artifact_type || !chunk.content) {
    return null;
  }

  const content = chunk.content;
  const lineCount =
    (chunk.metadata?.line_count as number) || content.split('\n').length;
  const charCount = (chunk.metadata?.char_count as number) || content.length;

  return {
    id: chunk.artifact_id,
    type: chunk.artifact_type,
    title: chunk.artifact_title || `${chunk.artifact_type} artifact`,
    content,
    language: chunk.artifact_language,
    lineCount,
    charCount,
    messageId: chunk.messageId,
    createdAt: new Date(),
  };
}

export default useArtifactStore;
