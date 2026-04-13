import { useEffect, useRef } from 'react';

/**
 * Hook that adds modal a11y behavior to a dialog container:
 * - Escape key to close
 * - Focus trap (Tab / Shift+Tab)
 * - Auto-focus on mount, restore focus on unmount
 *
 * Usage:
 *   const dialogRef = useModalA11y(onClose);
 *   <div ref={dialogRef} role="dialog" aria-modal="true" tabIndex={-1}>
 */
export function useModalA11y<T extends HTMLElement = HTMLDivElement>(
  onClose: () => void
) {
  const dialogRef = useRef<T>(null);
  const previousFocus = useRef<HTMLElement | null>(null);

  // Auto-focus + restore on unmount
  useEffect(() => {
    previousFocus.current = document.activeElement as HTMLElement;
    dialogRef.current?.focus();
    return () => {
      previousFocus.current?.focus();
    };
  }, []);

  // Escape key
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  // Focus trap
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    const handler = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      const focusable = dialog.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    dialog.addEventListener('keydown', handler);
    return () => dialog.removeEventListener('keydown', handler);
  }, []);

  return dialogRef;
}
