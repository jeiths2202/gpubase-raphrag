/**
 * Artifact Store
 *
 * Manages artifact state for the AI Agent chat.
 * Features:
 * - Artifact collection and display
 * - Panel state management (open/close, resize)
 * - Selected artifact tracking
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { ArtifactType, ArtifactLanguage } from '../api/agent.api';

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
 * Store state
 */
interface ArtifactState {
  // Artifacts list
  artifacts: Artifact[];

  // Panel state
  panel: ArtifactPanelState;

  // Actions - Artifacts
  addArtifact: (artifact: Artifact) => void;
  removeArtifact: (id: string) => void;
  clearArtifacts: () => void;
  updateArtifact: (id: string, updates: Partial<Artifact>) => void;

  // Actions - Panel
  openPanel: (artifactId?: string) => void;
  closePanel: () => void;
  togglePanel: () => void;
  setPanelWidth: (width: number) => void;
  selectArtifact: (id: string) => void;

  // Getters
  getArtifact: (id: string) => Artifact | undefined;
  getSelectedArtifact: () => Artifact | undefined;
}

// =============================================================================
// Constants
// =============================================================================

const MIN_PANEL_WIDTH = 300;
const MAX_PANEL_WIDTH = 1200;
const DEFAULT_PANEL_WIDTH = 500;

// =============================================================================
// Store
// =============================================================================

export const useArtifactStore = create<ArtifactState>()(
  persist(
    (set, get) => ({
      // Initial state
      artifacts: [],
      panel: {
        isOpen: false,
        width: DEFAULT_PANEL_WIDTH,
        selectedArtifactId: null,
      },

      // Artifact actions
      addArtifact: (artifact: Artifact) => {
        set((state) => {
          // Check if artifact with same ID already exists
          const exists = state.artifacts.some((a) => a.id === artifact.id);
          if (exists) {
            return state;
          }

          return {
            artifacts: [...state.artifacts, artifact],
            // Auto-select the new artifact and open panel
            panel: {
              ...state.panel,
              isOpen: true,
              selectedArtifactId: artifact.id,
            },
          };
        });
      },

      removeArtifact: (id: string) => {
        set((state) => {
          const newArtifacts = state.artifacts.filter((a) => a.id !== id);
          const wasSelected = state.panel.selectedArtifactId === id;

          return {
            artifacts: newArtifacts,
            panel: {
              ...state.panel,
              selectedArtifactId: wasSelected
                ? newArtifacts[newArtifacts.length - 1]?.id || null
                : state.panel.selectedArtifactId,
            },
          };
        });
      },

      clearArtifacts: () => {
        set({
          artifacts: [],
          panel: {
            ...get().panel,
            isOpen: false,
            selectedArtifactId: null,
          },
        });
      },

      updateArtifact: (id: string, updates: Partial<Artifact>) => {
        set((state) => ({
          artifacts: state.artifacts.map((a) =>
            a.id === id ? { ...a, ...updates } : a
          ),
        }));
      },

      // Panel actions
      openPanel: (artifactId?: string) => {
        const state = get();
        set({
          panel: {
            ...state.panel,
            isOpen: true,
            selectedArtifactId:
              artifactId ||
              state.panel.selectedArtifactId ||
              state.artifacts[state.artifacts.length - 1]?.id ||
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
        set((state) => ({
          panel: {
            ...state.panel,
            selectedArtifactId: id,
            isOpen: true,
          },
        }));
      },

      // Getters
      getArtifact: (id: string) => {
        return get().artifacts.find((a) => a.id === id);
      },

      getSelectedArtifact: () => {
        const state = get();
        if (!state.panel.selectedArtifactId) return undefined;
        return state.artifacts.find(
          (a) => a.id === state.panel.selectedArtifactId
        );
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
