/**
 * useChatScroll Hook
 *
 * Manages auto-scroll behavior for chat message containers with intelligent
 * scroll position detection and restoration from workspace store.
 *
 * Features:
 * - Auto-scroll to bottom when new messages arrive (only if user is at bottom)
 * - Detect when user is near bottom (within 100px threshold)
 * - Provide manual scroll-to-bottom function with smooth animation
 * - Track scroll state for persistent restoration via workspaceStore
 *
 * Business Rules:
 * - Auto-scroll enabled when: scrollTop + clientHeight >= scrollHeight - 100
 * - Save scroll position to workspaceStore on unmount
 * - Restore scroll position from workspaceStore on mount
 */

import { useRef, useEffect, useState, useCallback, RefObject } from 'react';

interface UseChatScrollOptions {
  /** Current messages array - used to trigger auto-scroll on new messages */
  messages: any[];
  /** Threshold in pixels to consider "at bottom" (default: 100) */
  bottomThreshold?: number;
  /** Enable scroll position persistence to workspace store */
  persistScrollPosition?: boolean;
  /** Callback to save scroll position (e.g., to workspaceStore) */
  onScrollPositionChange?: (scrollTop: number) => void;
  /** Initial scroll position to restore on mount */
  initialScrollPosition?: number;
}

interface UseChatScrollReturn {
  /** Ref to attach to scrollable container element */
  containerRef: RefObject<HTMLDivElement>;
  /** Whether user is currently at bottom of scroll container */
  isAtBottom: boolean;
  /** Manually scroll to bottom with optional smooth animation */
  scrollToBottom: (behavior?: ScrollBehavior) => void;
  /** Scroll event handler to track position changes */
  handleScroll: () => void;
}

export function useChatScroll({
  messages,
  bottomThreshold = 100,
  persistScrollPosition = false,
  onScrollPositionChange,
  initialScrollPosition
}: UseChatScrollOptions): UseChatScrollReturn {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const wasAtBottomRef = useRef(true); // Track previous state for auto-scroll logic

  /**
   * Check if user is currently at bottom of scroll container
   */
  const checkIsAtBottom = useCallback((): boolean => {
    const container = containerRef.current;
    if (!container) return true;

    const { scrollTop, scrollHeight, clientHeight } = container;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;

    return distanceFromBottom <= bottomThreshold;
  }, [bottomThreshold]);

  /**
   * Manually scroll to bottom with optional smooth behavior
   */
  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const container = containerRef.current;
    if (!container) return;

    container.scrollTo({
      top: container.scrollHeight,
      behavior
    });
  }, []);

  /**
   * Handle scroll event - update isAtBottom state and persist position
   */
  const handleScroll = useCallback(() => {
    const atBottom = checkIsAtBottom();
    setIsAtBottom(atBottom);
    wasAtBottomRef.current = atBottom;

    // Persist scroll position if enabled
    if (persistScrollPosition && containerRef.current && onScrollPositionChange) {
      onScrollPositionChange(containerRef.current.scrollTop);
    }
  }, [checkIsAtBottom, persistScrollPosition, onScrollPositionChange]);

  /**
   * Auto-scroll to bottom when new messages arrive
   *
   * Auto-scroll behavior:
   * 1. ALWAYS scroll when user sends a message (last message is from 'user')
   * 2. Only scroll for AI responses if user was already at bottom
   *
   * This prevents interrupting users reading old messages while ensuring
   * their own messages are always visible.
   */
  useEffect(() => {
    if (messages.length === 0) return;

    const lastMessage = messages[messages.length - 1];
    const isUserMessage = lastMessage?.role === 'user';

    // ALWAYS scroll to bottom when user sends a message
    if (isUserMessage) {
      scrollToBottom('smooth');
      return;
    }

    // For AI responses, only auto-scroll if user was at bottom before message arrived
    if (wasAtBottomRef.current) {
      scrollToBottom('smooth');
    }
  }, [messages.length, scrollToBottom, messages]);

  /**
   * Restore initial scroll position on mount
   */
  useEffect(() => {
    if (initialScrollPosition && containerRef.current) {
      // Use instant scroll for restoration (no animation)
      containerRef.current.scrollTop = initialScrollPosition;
    }
  }, []); // Only run on mount

  /**
   * Initialize scroll state on mount
   */
  useEffect(() => {
    const atBottom = checkIsAtBottom();
    setIsAtBottom(atBottom);
    wasAtBottomRef.current = atBottom;
  }, [checkIsAtBottom]);

  return {
    containerRef,
    isAtBottom,
    scrollToBottom,
    handleScroll
  };
}
