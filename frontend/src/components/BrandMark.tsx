import { useState } from "react";

/**
 * HelaGuide identity mark.
 *
 * Loads /logos/helaguidelogo.png when that file is present and falls back to
 * the inline SVG below if it is missing, so a missing asset never leaves a
 * broken image in the header.
 *
 * The fallback's three linked nodes rising left to right are the product
 * itself: a dependency path through services, which is what HelaGuide
 * produces and a plain chatbot does not.
 */
export default function BrandMark({ size = 40, title = "HelaGuide" }: { size?: number; title?: string }) {
  const [failed, setFailed] = useState(false);

  if (!failed) {
    return (
      <img
        src="/logos/helaguidelogo.png"
        alt={title}
        width={size}
        height={size}
        onError={() => setFailed(true)}
      />
    );
  }

  return (
    <svg width={size} height={size} viewBox="0 0 48 48" role="img" aria-label={title} focusable="false">
      <defs>
        <linearGradient id="hg-ring" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--amber-300)" />
          <stop offset="100%" stopColor="var(--amber-600)" />
        </linearGradient>
      </defs>

      <circle cx="24" cy="24" r="22" fill="var(--navy-800)" />
      <circle cx="24" cy="24" r="22" fill="none" stroke="url(#hg-ring)" strokeWidth="3" />

      <path d="M14 32 L24 24 L34 16" fill="none" stroke="var(--amber-400)" strokeWidth="2.5" strokeLinecap="round" />
      <circle cx="14" cy="32" r="4.4" fill="var(--amber-400)" />
      <circle cx="24" cy="24" r="4.4" fill="var(--amber-300)" />
      <circle cx="34" cy="16" r="4.4" fill="#ffffff" />

      <rect x="15" y="38" width="18" height="2.2" rx="1.1" fill="var(--amber-500)" opacity=".85" />
    </svg>
  );
}
