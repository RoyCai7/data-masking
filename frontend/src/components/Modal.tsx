import { useEffect, useRef, type ReactNode, type MouseEvent } from 'react';
import { motion } from 'framer-motion';
import { XMarkIcon } from '@heroicons/react/24/outline';

interface ModalProps {
  onClose: () => void;
  title: string;
  subtitle?: string;
  icon?: ReactNode;
  children: ReactNode;
  /** Width class, defaults to max-w-lg */
  widthClass?: string;
  /** Height class for full-height modals */
  heightClass?: string;
}

/**
 * Accessible modal wrapper with:
 * - Escape key to close
 * - Focus trap (Tab / Shift+Tab)
 * - ARIA role=dialog + aria-modal
 * - Click-outside to close
 * - Auto-focus on open, restore focus on close
 */
export default function Modal({
  onClose,
  title,
  subtitle,
  icon,
  children,
  widthClass = 'max-w-lg',
  heightClass,
}: ModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);

  // Save current focus and restore on unmount
  useEffect(() => {
    previousFocus.current = document.activeElement as HTMLElement;
    // Focus the dialog itself on open
    dialogRef.current?.focus();
    return () => {
      previousFocus.current?.focus();
    };
  }, []);

  // Escape key handler
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

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
      onClick={onClose}
      aria-hidden="true"
    >
      <motion.div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        initial={{ scale: 0.96, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.96, opacity: 0 }}
        onClick={(e: MouseEvent<HTMLDivElement>) => e.stopPropagation()}
        className={`bg-white rounded-2xl shadow-xl w-full ${widthClass} ${heightClass || ''} overflow-hidden flex flex-col outline-none`}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            {icon}
            <div>
              <h2 className="text-lg font-bold text-gray-900">{title}</h2>
              {subtitle && <p className="text-xs text-gray-500">{subtitle}</p>}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-full hover:bg-gray-100 transition-colors"
            aria-label="Close"
          >
            <XMarkIcon className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Content */}
        {children}
      </motion.div>
    </motion.div>
  );
}
