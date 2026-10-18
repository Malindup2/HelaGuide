import { ChevronRight } from "lucide-react";

const NOTICES = [
  {
    id: 1,
    tag: "GAZETTE EXTRAORDINARY",
    title: "No. 2381/14: Revised Digital Citizenship & Identity Card Issuance Guidelines 2026",
    date: "NEW",
  },
  {
    id: 2,
    tag: "PUBLIC NOTICE",
    title: "Online Pre-Appointment System mandatory for Colombo General Registrar Division",
    date: "UPDATE",
  },
  {
    id: 3,
    tag: "E-GOVERNMENT",
    title: "GIC 1919 Hotline integrated with HelaGuide AI Orchestrator for 24/7 assistance",
    date: "FEATURED",
  },
  {
    id: 4,
    tag: "MOTOR TRAFFIC",
    title: "Biometric Driving License Renewal services extended to Northern & Eastern Provinces",
    date: "NOTICE",
  },
  {
    id: 5,
    tag: "TRADE & BUSINESS",
    title: "Single-Window Import/Export Permit Portal registration deadline announced",
    date: "DEADLINE",
  },
];

export default function NoticeMarquee() {
  return (
    <aside
      className="bg-navy-950 border-b border-amber-500/20 text-slate-200 text-xs py-2 px-4 flex items-center overflow-hidden select-none relative z-10 shadow-sm"
      aria-label="Official Notices and Gazettes"
    >
      <div className="relative flex-1 overflow-hidden flex items-center h-6">
        <div className="flex items-center gap-10 whitespace-nowrap animate-marquee hover:[animation-play-state:paused] cursor-pointer">
          {NOTICES.concat(NOTICES).map((notice, idx) => (
            <div key={`${notice.id}-${idx}`} className="inline-flex items-center gap-2 group shrink-0">
              <span className="bg-white/10 text-amber-400 text-[10px] font-bold tracking-widest uppercase px-2 py-0.5 rounded">
                {notice.tag}
              </span>
              <span className="text-slate-300 group-hover:text-amber-300 font-medium transition-colors">
                {notice.title}
              </span>
              <span className="text-[10px] font-bold text-amber-400 bg-amber-500/15 border border-amber-500/30 px-1.5 py-0.5 rounded">
                {notice.date}
              </span>
              <ChevronRight size={12} className="text-slate-500 group-hover:text-amber-400 group-hover:translate-x-0.5 transition-all" />
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}
