import { useEffect, useRef } from "react";
import { X } from "lucide-react";
export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const active = document.activeElement as HTMLElement;
    ref.current?.showModal();
    return () => {
      ref.current?.close();
      active?.focus();
    };
  }, []);
  return (
    <dialog
      className="ops-dialog"
      ref={ref}
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <header>
        <h2>{title}</h2>
        <button
          className="icon-btn"
          aria-label="Close runtime dialog"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </header>
      <div className="ops-dialog-body">{children}</div>
    </dialog>
  );
}
