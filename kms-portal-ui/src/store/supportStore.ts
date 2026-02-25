/**
 * Support Store
 *
 * Zustand store for support dashboard state management.
 * Tracks support sessions and waiting count for header badge.
 */

import { create } from 'zustand';
import type { SessionInfo } from '../api/premium-support.api';

interface SupportState {
  sessions: SessionInfo[];
  waitingCount: number;
  activeCount: number;
  isPolling: boolean;

  setSessions: (sessions: SessionInfo[]) => void;
  setIsPolling: (polling: boolean) => void;
  reset: () => void;
}

export const useSupportStore = create<SupportState>((set) => ({
  sessions: [],
  waitingCount: 0,
  activeCount: 0,
  isPolling: false,

  setSessions: (sessions: SessionInfo[]) => {
    const waitingCount = sessions.filter((s) => s.status === 'waiting').length;
    const activeCount = sessions.filter((s) => s.status === 'active').length;
    set({ sessions, waitingCount, activeCount });
  },

  setIsPolling: (polling: boolean) => set({ isPolling: polling }),

  reset: () => set({ sessions: [], waitingCount: 0, activeCount: 0, isPolling: false }),
}));
