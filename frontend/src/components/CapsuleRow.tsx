import capsuleData from "../data/capsules.json";

export default function CapsuleRow({
  onPick,
  compact = false,
  lang = "en",
}: {
  onPick: (text: string) => void;
  compact?: boolean;
  lang?: string;
}) {
  // If user selected 'si', prioritize Sinhala capsules or show mixed
  const items = capsuleData.capsules.filter((c) => lang === "si" ? true : c.lang === "en");

  return (
    <div className="flex flex-wrap items-center justify-center gap-2.5 mt-5 max-w-4xl mx-auto px-4">
      {items.map((c) => (
        <button
          key={c.id}
          type="button"
          onClick={() => onPick(c.label)}
          className={`group inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 hover:bg-amber-500 text-slate-200 hover:text-navy-950 shadow-sm backdrop-blur-md transition-all duration-200 cursor-pointer active:scale-95 ${
            compact ? "px-3 py-1 text-xs" : "px-4 py-2 text-xs sm:text-sm font-medium"
          }`}
        >
          <span>{c.label}</span>
          {c.hint && !compact && (
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-white/15 text-slate-300 group-hover:bg-navy-900/30 group-hover:text-navy-950 font-mono font-medium transition-colors">
              {c.hint}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
