import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import type { Mark } from '../presentation';

const base = { className: 'gc-icon', viewBox: '0 0 16 16', 'aria-hidden': true, fill: 'none', stroke: 'currentColor', strokeWidth: 1.4, strokeLinecap: 'round', strokeLinejoin: 'round' } as const;
export const DocIcon = () => <svg {...base}><path d="M4 1.8h5.2L12.5 5v9.2H4z M9.2 1.8V5h3.3" /></svg>;
export const FeeIcon = () => <svg {...base}><circle cx="8" cy="8" r="6" /><path d="M8 4.6v6.8 M6.3 6.4c0-1.5 3.4-1.5 3.4 0S6.3 8.4 6.3 9.9c0 1.5 3.4 1.5 3.4 0" /></svg>;
export const ChevronIcon = () => <svg {...base} className="gc-icon gc-chev"><path d="M4 6l4 4 4-4" /></svg>;
export const SlidersIcon = () => <svg {...base}><path d="M2 5h12 M2 11h12" /><circle cx="6" cy="5" r="1.6" fill="currentColor" /><circle cx="10.5" cy="11" r="1.6" fill="currentColor" /></svg>;
export const ListIcon = () => <svg {...base}><path d="M5.5 4h8 M5.5 8h8 M5.5 12h8 M2.5 4h.1 M2.5 8h.1 M2.5 12h.1" /></svg>;
export const MapIcon = () => <svg {...base}><circle cx="3.5" cy="8" r="1.5" /><circle cx="12.5" cy="4" r="1.5" /><circle cx="12.5" cy="12" r="1.5" /><path d="M5 8c3 0 3-4 6-4 M5 8c3 0 3 4 6 4" /></svg>;
export const InfoIcon = () => <svg {...base}><circle cx="8" cy="8" r="6" /><path d="M8 7.2v4 M8 4.8h.01" /></svg>;
export const CloseIcon = () => <svg {...base}><path d="M4 4l8 8 M12 4l-8 8" /></svg>;

/** A route or common marker. Letters mark alternatives; plain actions get a quiet dot, never a sequence number. */
export function MarkDot({ mark }: { mark: Mark }) {
  return <span className={`gc-mark gc-mark-${mark.kind}`} aria-hidden="true">{mark.label}</span>;
}

/** One accessible dialog: a bottom sheet in narrow containers, a side panel in wide ones. */
export function Sheet({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current, previous = document.activeElement as HTMLElement | null;
    if (!dialog) return;
    if (typeof dialog.showModal === 'function') { if (!dialog.open) dialog.showModal(); } else dialog.setAttribute('open', '');
    // Removing the element ends the modal; calling close() here would fire onClose again.
    return () => { previous?.focus?.(); };
  }, []);
  return <dialog ref={ref} className={`gc-sheet${wide ? ' gc-sheet-wide' : ''}`} aria-label={title} onClose={onClose} onCancel={onClose}
    onClick={e => { if (e.target === ref.current) onClose(); }}>
    <div className="gc-sheet-head"><h2>{title}</h2><button type="button" className="gc-icon-btn" aria-label={`Close ${title}`} onClick={onClose}><CloseIcon /></button></div>
    <div className="gc-sheet-body">{children}</div>
  </dialog>;
}
