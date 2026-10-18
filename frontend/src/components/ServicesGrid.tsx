import { useState } from "react";
import {
  Wheat, Landmark, UserCheck, Radio, GraduationCap, Briefcase,
  TreePine, HeartPulse, Home, Scale, Store, Plane, ArrowRight, Search, Sparkles,
} from "lucide-react";

const SERVICES = [
  { id: "agri", icon: <Wheat size={22} />, title: "Agriculture, Livestock & Fisheries", subs: ["Approval & Registration", "Permits & Licenses", "Subsidies & Assistance"], href: "https://gic.gov.lk/services/agriculture-livestock-fisheries", count: "142 Services" },
  { id: "banking", icon: <Landmark size={22} />, title: "Banking, Tax & Insurance", subs: ["Leasing Facilities", "Miscellaneous", "Bank Accounts"], href: "https://gic.gov.lk/services/banking-tax-insurance", count: "98 Services" },
  { id: "citizen", icon: <UserCheck size={22} />, title: "Citizen's Registrations", subs: ["Citizenship", "Birth & Marriage", "NIC & Passport"], href: "https://gic.gov.lk/services/citizens-registrations", count: "215 Services" },
  { id: "media", icon: <Radio size={22} />, title: "Communication & Media", subs: ["Languages", "Postal Service", "Information Services"], href: "https://gic.gov.lk/services/communication-media", count: "64 Services" },
  { id: "edu", icon: <GraduationCap size={22} />, title: "Education & Training", subs: ["Education Publications", "Pre-School Education", "School Education"], href: "https://gic.gov.lk/services/education-training", count: "180 Services" },
  { id: "job", icon: <Briefcase size={22} />, title: "Employment Information", subs: ["Career Guidance", "Employment Promotion", "Career Publications"], href: "https://gic.gov.lk/services/employment-information", count: "112 Services" },
  { id: "env", icon: <TreePine size={22} />, title: "Environment", subs: ["Disaster Relief", "Disaster Management", "Environmental Protection"], href: "https://gic.gov.lk/services/environment", count: "76 Services" },
  { id: "health", icon: <HeartPulse size={22} />, title: "Health, Well Being & Social Service", subs: ["Health Assistance", "Child Care", "Social Service"], href: "https://gic.gov.lk/services/health-wellbeing-social-service", count: "154 Services" },
  { id: "housing", icon: <Home size={22} />, title: "Housing, Property & Utilities", subs: ["Infrastructure", "Housing & Property", "Building Regulations"], href: "https://gic.gov.lk/services/housing-property-utilities", count: "130 Services" },
  { id: "justice", icon: <Scale size={22} />, title: "Justice, Law & Rights", subs: ["Consumer Protection", "Legislature & Executive", "Legal Assistance"], href: "https://gic.gov.lk/services/justice-law-rights", count: "88 Services" },
  { id: "trade", icon: <Store size={22} />, title: "Trade, Business & Industry", subs: ["Regulation of Trade", "Trade Promotion", "Exports & Permits"], href: "https://gic.gov.lk/services/trade-business-industry", count: "165 Services" },
  { id: "travel", icon: <Plane size={22} />, title: "Travel, Tourism & Leisure", subs: ["Transport", "Leisure & Visas", "National Museums"], href: "https://gic.gov.lk/services/travel-tourism-leisure", count: "93 Services" },
];

export default function ServicesGrid() {
  const [searchQuery, setSearchQuery] = useState("");

  const filteredServices = SERVICES.filter((s) =>
    s.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.subs.some((sub) => sub.toLowerCase().includes(searchQuery.toLowerCase())),
  );

  return (
    <section className="py-20 bg-paper border-t border-line" aria-labelledby="eservices-title">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-12">
          <div>
            <span className="inline-flex items-center gap-2 text-[11px] uppercase tracking-widest font-extrabold text-amber-600 bg-amber-500/10 border border-amber-500/20 px-3.5 py-1.5 rounded-full mb-3">
              <Sparkles size={13} className="text-amber-500" />
              E-Services Directory
            </span>
            <h2 id="eservices-title" className="text-3xl sm:text-4xl font-extrabold tracking-tight text-ink">
              Government Services by Category
            </h2>
            <p className="text-base text-ink-2 mt-2 max-w-2xl">
              Browse verified digital services and information portals across 12 primary government domains.
            </p>
          </div>

          <div className="relative w-full md:w-80">
            <Search size={18} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-3 pointer-events-none" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search category or service..."
              className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-line bg-paper-2 text-ink text-sm placeholder:text-ink-3 focus:outline-none focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20 transition-all"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-6">
          {filteredServices.map((s) => (
            <a
              key={s.id}
              className="group relative flex flex-col bg-paper-2 border border-line rounded-2xl p-6 no-underline text-inherit transition-all duration-300 hover:border-amber-400/60 hover:shadow-xl hover:shadow-amber-500/5 hover:-translate-y-1.5 overflow-hidden"
              href={s.href}
              target="_blank"
              rel="noreferrer noopener"
            >
              <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-amber-500 to-amber-400 scale-x-0 origin-left transition-transform duration-300 group-hover:scale-x-100" />
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 rounded-xl grid place-items-center bg-gradient-to-br from-amber-500/15 to-amber-500/5 text-amber-600 border border-amber-500/20 shadow-xs group-hover:scale-110 group-hover:bg-amber-500 group-hover:text-navy-950 transition-all duration-300">
                  {s.icon}
                </div>
                <span className="text-[11px] font-bold text-ink-3 bg-paper border border-line px-2.5 py-1 rounded-full group-hover:border-amber-500/30 group-hover:text-amber-600 transition-colors">
                  {s.count}
                </span>
              </div>
              <h3 className="text-base font-bold text-ink mb-3 leading-snug group-hover:text-amber-600 transition-colors">
                {s.title}
              </h3>
              <div className="flex flex-wrap gap-1.5 mb-6">
                {s.subs.map((sub) => (
                  <span key={sub} className="text-[11px] font-medium text-ink-2 bg-paper border border-line/80 px-2 py-0.5 rounded-md group-hover:border-amber-500/20 transition-colors">
                    {sub}
                  </span>
                ))}
              </div>
              <div className="mt-auto pt-4 border-t border-line/60 flex items-center justify-between text-xs font-bold text-amber-600">
                <span>Explore Section</span>
                <div className="w-6 h-6 rounded-full bg-amber-500/10 grid place-items-center group-hover:bg-amber-500 group-hover:text-navy-950 transition-all">
                  <ArrowRight size={13} className="group-hover:translate-x-0.5 transition-transform" />
                </div>
              </div>
            </a>
          ))}
        </div>

        {filteredServices.length === 0 && (
          <div className="text-center py-16 bg-paper-2 rounded-2xl border border-line">
            <p className="text-ink-2 text-base font-medium">No service categories matched &quot;{searchQuery}&quot;.</p>
            <button
              onClick={() => setSearchQuery("")}
              className="mt-4 px-4 py-2 text-xs font-bold uppercase tracking-wider text-amber-600 bg-amber-500/10 rounded-lg hover:bg-amber-500 hover:text-navy-950 transition-all cursor-pointer border-none"
            >
              Clear Search
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
