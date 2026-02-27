import { useState, useRef, useMemo, useCallback } from 'react';

/**
 * Chat 입력창에서 이전 전송 메시지를 ArrowUp/Down으로 탐색하는 훅.
 * 터미널 히스토리와 동일한 UX.
 */
export function useInputHistory(messages: Array<{ role: string; content: string }>) {
  const [historyIndex, setHistoryIndex] = useState(-1); // -1 = 현재 입력 모드
  const draftRef = useRef(''); // 히스토리 진입 전 입력 텍스트 보존

  // user 메시지만 역순(최신 먼저)으로 추출
  const userMessages = useMemo(
    () => messages.filter(m => m.role === 'user').map(m => m.content).reverse(),
    [messages]
  );

  const handleHistoryNav = useCallback(
    (
      e: React.KeyboardEvent<HTMLTextAreaElement>,
      currentInput: string,
      setInput: (v: string) => void
    ) => {
      const textarea = e.currentTarget;
      const isAtStart = textarea.selectionStart === 0 && textarea.selectionEnd === 0;
      const isAtEnd = textarea.selectionStart === textarea.value.length;
      const isEmpty = currentInput.trim() === '';

      if (e.key === 'ArrowUp' && (isEmpty || isAtStart)) {
        if (userMessages.length === 0) return;
        e.preventDefault();
        if (historyIndex === -1) {
          draftRef.current = currentInput;
        }
        const newIndex = Math.min(historyIndex + 1, userMessages.length - 1);
        setHistoryIndex(newIndex);
        setInput(userMessages[newIndex]);
      }

      if (e.key === 'ArrowDown' && (isEmpty || isAtEnd)) {
        if (historyIndex <= -1) return;
        e.preventDefault();
        const newIndex = historyIndex - 1;
        setHistoryIndex(newIndex);
        if (newIndex === -1) {
          setInput(draftRef.current);
        } else {
          setInput(userMessages[newIndex]);
        }
      }
    },
    [historyIndex, userMessages]
  );

  // 메시지 전송 후 리셋
  const resetHistory = useCallback(() => {
    setHistoryIndex(-1);
    draftRef.current = '';
  }, []);

  return { handleHistoryNav, resetHistory };
}
