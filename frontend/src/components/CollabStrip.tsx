import { useState } from "react";

/** Partnership band, echoing the GIC homepage rhythm.
 *
 * If a logo file is missing the tile falls back to its text label rather than
 * rendering a broken image. */
const PARTNERS = [
  { id: "gic", src: "/logos/collab1.png", alt: "Government Information Centre", label: "Government Information Centre" },
  { id: "icta", src: "/logos/collab2.jpg", alt: "Information and Communication Technology Agency", label: "ICTA" },
];

function PartnerLogo({ partner }: { partner: (typeof PARTNERS)[number] }) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <span className="inline-flex items-center h-[52px] px-4 border border-dashed rounded-md text-xs font-semibold border-line-2 text-ink-2">
        {partner.label}
      </span>
    );
  }
  return (
    <img
      className="h-[52px] w-auto max-w-[240px] object-contain bg-white border border-line rounded-md px-4 py-2 shadow-sm"
      src={partner.src}
      alt={partner.alt}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}

export default function CollabStrip({ heading = "In collaboration with" }: { heading?: string }) {
  return (
    <section className="mt-12" aria-label="Partners">
      <div className="flex items-center gap-4 text-[11px] uppercase tracking-widest font-bold text-ink-3 before:flex-auto before:h-px before:bg-line after:flex-auto after:h-px after:bg-line">
        <span>{heading}</span>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-6 mt-6">
        {PARTNERS.map((p) => <PartnerLogo key={p.id} partner={p} />)}
      </div>
    </section>
  );
}
