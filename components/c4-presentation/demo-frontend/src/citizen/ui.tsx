import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';

export { ChevronIcon, CloseIcon, DocIcon, FeeIcon, InfoIcon, ListIcon, MapIcon, SlidersIcon } from '../guidance-v2/card/parts';

const base = { className: 'gc-icon', viewBox: '0 0 16 16', 'aria-hidden': true, fill: 'none', stroke: 'currentColor', strokeWidth: 1.4, strokeLinecap: 'round', strokeLinejoin: 'round' } as const;
export const ThumbUpIcon = () => <svg {...base}><path d="M5 7v6H2.5V7z M5 7l3-5c1.2 0 1.8.9 1.5 2L9 6.5h3.3c.9 0 1.5.8 1.3 1.6l-.9 4c-.2.6-.7.9-1.3.9H5" /></svg>;
export const ThumbDownIcon = () => <svg {...base}><path d="M5 9V3H2.5v6z M5 9l3 5c1.2 0 1.8-.9 1.5-2L9 9.5h3.3c.9 0 1.5-.8 1.3-1.6l-.9-4c-.2-.6-.7-.9-1.3-.9H5" /></svg>;
export const ExpandIcon = () => <svg {...base}><path d="M9.5 2.5h4v4 M6.5 13.5h-4v-4 M13.5 2.5L9 7 M2.5 13.5L7 9" /></svg>;
export const EyeIcon = () => <svg {...base}><path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" /><circle cx="8" cy="8" r="2" /></svg>;
export const MenuIcon = () => <svg {...base}><path d="M2.5 4h11 M2.5 8h11 M2.5 12h11" /></svg>;

export type SheetVariant = 'bottom' | 'panel' | 'modal';

/** One accessible dialog. Bottom sheet on phones, side panel or centred modal on wide screens. Focus returns on close. */
export function Sheet({ title, onClose, children, variant = 'bottom' }: { title: string; onClose: () => void; children: ReactNode; variant?: SheetVariant }) {
  const ref = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    // Remember the control that opened the sheet once. React StrictMode replays this effect, and a second read would see the sheet's own focus.
    opener.current ??= document.activeElement as HTMLElement | null;
    if (typeof dialog.showModal === 'function') { if (!dialog.open) dialog.showModal(); } else dialog.setAttribute('open', '');
    return () => { if (opener.current?.isConnected) opener.current.focus(); };
  }, []);
  return <dialog ref={ref} className={`cz-sheet cz-sheet-${variant}`} aria-label={title} onClose={onClose} onCancel={onClose}
    onClick={e => { if (e.target === ref.current) onClose(); }}>
    <div className="cz-sheet-head"><h2>{title}</h2><button type="button" className="cz-iconbtn" aria-label={`Close ${title}`} onClick={onClose}><svg className="gc-icon" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"><path d="M4 4l8 8 M12 4l-8 8" /></svg></button></div>
    <div className="cz-sheet-body">{children}</div>
  </dialog>;
}
