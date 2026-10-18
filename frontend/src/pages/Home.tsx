import { useState, useRef } from "react";
import { Link } from "react-router-dom";
import {
  Phone, Users, Zap, ShieldCheck, Clock, Target, Eye,
  Sparkles, AlertTriangle, CheckCircle2, RotateCcw,
  SlidersHorizontal,
} from "lucide-react";
import BrandMark from "../components/BrandMark";
import NoticeMarquee from "../components/NoticeMarquee";
import LanguageSwitch from "../components/LanguageSwitch";
import Composer from "../components/Composer";
import CapsuleRow from "../components/CapsuleRow";
import CollabStrip from "../components/CollabStrip";
import ServicesGrid from "../components/ServicesGrid";
import GetInTouch from "../components/GetInTouch";
import ContactSection from "../components/ContactSection";
import { askForGuidance } from "../api/gateway";
import type { Render } from "../api/types";

const sessionId = `anon-${Math.random().toString(36).slice(2, 8)}`;

const CORE_VALUES = [
  {
    icon: Users,
    title: "Citizen-Centric",
    desc: "Services designed with citizens in mind",
  },
  {
    icon: Zap,
    title: "Fast & Efficient",
    desc: "Quick access to government services",
  },
  {
    icon: ShieldCheck,
    title: "Transparent",
    desc: "Open and accountable governance",
  },
  {
    icon: Clock,
    title: "Reliable",
    desc: "24/7 support and information access",
  },
];

export default function Home() {
  const [lang, setLang] = useState<string>("en");
  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [result, setResult] = useState<Render | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const resultsRef = useRef<HTMLDivElement>(null);

  async function handleAsk(textToAsk?: string) {
    const q = (textToAsk ?? query).trim();
    if (!q) return;

    setActiveQuery(q);
    setBusy(true);
    setError(null);

    // Scroll to results area smoothly
    setTimeout(() => {
      resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 100);

    try {
      const data = await askForGuidance(sessionId, q);
      setResult(data);
    } catch (err: unknown) {
      console.error("Guidance request failed:", err);
      setError(
        err instanceof Error
          ? err.message
          : "Unable to connect to the HelaGuide guidance orchestrator. Please ensure the backend gateway service is running on port 8000."
      );
    } finally {
      setBusy(false);
    }
  }

  function handlePickCapsule(labelText: string) {
    setQuery(labelText);
    handleAsk(labelText);
  }

  function clearResults() {
    setResult(null);
    setError(null);
    setQuery("");
    setActiveQuery("");
  }

  return (
    <div className="min-h-screen bg-paper text-ink font-sans selection:bg-amber-500 selection:text-navy-950">
      <a href="#main" className="skip-link">
        Skip to content
      </a>

      {/* ── Sticky Topbar + Navigation ── */}
      <header className="sticky top-0 z-50 shadow-sm transition-colors">
        {/* Government Top Bar */}
        <div className="bg-navy-950 text-slate-300 border-b border-white/10 py-1.5 px-4 text-xs">
          <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="inline-flex items-center gap-1.5 bg-amber-500 text-navy-950 font-bold px-2.5 py-0.5 rounded-full text-[11px] tracking-wide shadow-xs">
                <Phone size={11} className="stroke-[2.5]" />
                1919
              </span>
              <span className="hidden sm:inline-flex items-center gap-2 text-slate-300 font-medium text-[11px]">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                RESEARCH PROTOTYPE · SLIIT IT4010
              </span>
            </div>

            <div className="flex items-center gap-3">
              <LanguageSwitch currentLang={lang} onSelectLang={setLang} />
            </div>
          </div>
        </div>

        {/* Main Nav */}
        <nav className="bg-paper/98 backdrop-blur-md border-b border-line py-3 px-4 sm:px-6 lg:px-8 w-full" aria-label="Main navigation">
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <Link to="/" className="flex items-center gap-3 no-underline text-inherit group">
              <span className="transition-transform group-hover:scale-105">
                <BrandMark size={38} />
              </span>
              <div>
                <div className="text-lg font-black tracking-tight text-ink flex items-center gap-1.5 leading-none">
                  HelaGuide
                  <span className="text-[10px] font-extrabold text-amber-600 bg-amber-500/15 border border-amber-500/25 px-1.5 py-0.5 rounded">
                    AI
                  </span>
                </div>
                <div className="text-[11px] font-medium text-ink-3 mt-1 tracking-wider uppercase">
                  Government Information Service
                </div>
              </div>
            </Link>

            <div className="flex items-center gap-3">
              <a
                href="#about-title"
                className="hidden md:inline-flex items-center text-xs font-semibold text-ink-2 hover:text-amber-600 px-3 py-1.5 rounded-lg hover:bg-paper-2 transition-colors no-underline"
              >
                About
              </a>
              <a
                href="#eservices-title"
                className="hidden md:inline-flex items-center text-xs font-semibold text-ink-2 hover:text-amber-600 px-3 py-1.5 rounded-lg hover:bg-paper-2 transition-colors no-underline"
              >
                E-Services
              </a>
              <a
                href="#contact-title"
                className="hidden sm:inline-flex items-center text-xs font-semibold text-ink-2 hover:text-amber-600 px-3 py-1.5 rounded-lg hover:bg-paper-2 transition-colors no-underline"
              >
                Help & Support
              </a>

              <Link
                to="/admin"
                className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-2 hover:text-amber-600 border border-line hover:border-amber-500/40 px-3.5 py-1.5 rounded-xl bg-paper hover:bg-paper-2 transition-all no-underline shadow-2xs"
              >
                <SlidersHorizontal size={13} className="text-amber-500" />
                <span>C2 Admin</span>
              </Link>
            </div>
          </div>
        </nav>
      </header>

      {/* ── Official Gazettes & Notices Marquee ── */}
      <NoticeMarquee />

      {/* ── Main Content Area ── */}
      <main id="main">
        {/* ── Hero Section ── */}
        <section
          className="relative bg-gradient-to-b from-navy-950 via-navy-900 to-slate-900 text-white pt-16 pb-28 px-4 text-center overflow-hidden"
          aria-label="Government Workflow Orchestrator"
        >
          {/* Subtle background glow effect */}
          <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[550px] h-[350px] bg-amber-500/10 rounded-full blur-3xl pointer-events-none" />

          <div className="relative max-w-4xl mx-auto z-10">
            {/* Official Badge */}
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-white/20 bg-white/10 text-amber-300 text-xs font-semibold mb-6 backdrop-blur-md shadow-sm">
              <Sparkles size={13} className="text-amber-400" />
              AI-powered government service guide
            </div>

            {/* Headline */}
            <h1 className="text-3xl sm:text-5xl lg:text-6xl font-black tracking-tight leading-[1.1] text-white">
              <span className="text-amber-400">Ask once.</span> Get the full workflow.
            </h1>

            {/* Lede */}
            <p className="mt-4 text-sm sm:text-base md:text-lg text-slate-300 max-w-2xl mx-auto leading-relaxed font-normal">
              Tell HelaGuide what you need — a passport, an NIC, a birth certificate — and get
              the ordered steps, documents, and fees across every department involved, sourced
              from official government sites.
            </p>

            {/* Prompt Composer Box */}
            <div className="mt-8">
              <Composer
                value={query}
                onChange={setQuery}
                onSubmit={() => handleAsk()}
                busy={busy}
                placeholder={
                  lang === "si"
                    ? "ඕනෑම රාජ්‍ය සේවාවක් ගැන අසන්න… e.g. පාස්පෝට් අලුත් කිරීම"
                    : lang === "ta"
                    ? "எந்த அரசு சேவை பற்றியும் கேளுங்கள்… e.g. கடவுச்சීட்டு புதுப்பித்தல்"
                    : "Ask about any government service… e.g. Renew the passport"
                }
              />
            </div>

            {/* Suggestion Capsules */}
            <CapsuleRow onPick={handlePickCapsule} lang={lang} />

            {/* Trust Strip */}
            <div className="flex flex-wrap items-center justify-center gap-3 sm:gap-6 mt-10 text-xs sm:text-sm text-slate-400 font-medium">
              <span>
                <strong className="text-white font-mono font-bold text-sm sm:text-base">1,487</strong> Services mapped
              </span>
              <span className="w-1 h-1 rounded-full bg-slate-600" />
              <span>
                <strong className="text-white font-mono font-bold text-sm sm:text-base">656</strong> Government offices
              </span>
              <span className="w-1 h-1 rounded-full bg-slate-600" />
              <span className="inline-flex items-center gap-1.5 text-amber-400 font-semibold">
                <CheckCircle2 size={14} className="text-emerald-400" />
                Verified against official sources
              </span>
            </div>
          </div>

          {/* Elliptical wave bottom transition */}
          <div
            className="absolute -bottom-0.5 left-0 right-0 h-14 bg-paper pointer-events-none"
            style={{ clipPath: "ellipse(55% 100% at 50% 100%)" }}
          />
        </section>

        {/* ── Guidance Results View (Interactive Real Backend) ── */}
        <div ref={resultsRef} className="scroll-mt-24">
          {(busy || result || error) && (
            <section className="py-12 bg-paper-2 border-b border-line" aria-label="Workflow Results">
              <div className="max-w-4xl mx-auto px-4 sm:px-6">
                {/* Thinking / Loading state */}
                {busy && (
                  <div className="bg-paper border border-amber-500/30 rounded-2xl p-8 shadow-lg text-center animate-pulse space-y-4">
                    <div className="w-12 h-12 rounded-full bg-amber-500/10 text-amber-600 grid place-items-center mx-auto border border-amber-500/20">
                      <Zap size={24} className="animate-bounce" />
                    </div>
                    <h3 className="text-lg font-bold text-ink">
                      Orchestrating guidance for &quot;{activeQuery}&quot;...
                    </h3>
                    <p className="text-xs text-ink-3 max-w-md mx-auto">
                      Querying knowledge graph, resolving inter-agency prerequisites, and structuring the ordered steps with fees and requirements.
                    </p>
                  </div>
                )}

                {/* Error State */}
                {error && !busy && (
                  <div className="bg-rose-50 dark:bg-rose-950/20 border border-rose-200 dark:border-rose-900/50 rounded-2xl p-6 sm:p-8">
                    <div className="flex items-start gap-4">
                      <div className="w-10 h-10 rounded-xl bg-rose-500/10 text-rose-600 grid place-items-center shrink-0">
                        <AlertTriangle size={20} />
                      </div>
                      <div className="flex-1">
                        <h4 className="text-base font-bold text-rose-900 dark:text-rose-200">
                          Guidance Service Notice
                        </h4>
                        <p className="text-sm text-rose-700 dark:text-rose-300 mt-1 leading-relaxed">
                          {error}
                        </p>
                        <div className="mt-4 flex gap-3">
                          <button
                            type="button"
                            onClick={() => handleAsk()}
                            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold text-white bg-rose-600 hover:bg-rose-700 transition-all cursor-pointer border-none shadow-sm"
                          >
                            <RotateCcw size={13} />
                            Retry Query
                          </button>
                          <button
                            type="button"
                            onClick={clearResults}
                            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-rose-800 dark:text-rose-200 bg-rose-100 dark:bg-rose-900/40 hover:bg-rose-200 transition-all cursor-pointer border-none"
                          >
                            Dismiss
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Real Result Success View */}
                {result && !busy && (
                  <div className="bg-paper border border-line rounded-2xl p-6 sm:p-8 shadow-xl">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-6 border-b border-line gap-4">
                      <div>
                        <div className="inline-flex items-center gap-1.5 text-xs font-bold text-emerald-600 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded-full mb-2">
                          <CheckCircle2 size={13} />
                          Verified Citizen Workflow
                        </div>
                        <h2 className="text-2xl font-extrabold text-ink tracking-tight">
                          {activeQuery}
                        </h2>
                        <p className="text-xs text-ink-3 mt-1">
                          {result.steps.length} sequential step{result.steps.length === 1 ? "" : "s"} required across relevant government authorities
                        </p>
                      </div>

                      <button
                        type="button"
                        onClick={clearResults}
                        className="self-start sm:self-auto text-xs font-bold text-ink-2 hover:text-amber-600 bg-paper-2 hover:bg-paper-3 border border-line px-3 py-1.5 rounded-xl transition-all cursor-pointer"
                      >
                        Ask Another Question
                      </button>
                    </div>

                    {/* Ordered Workflow Steps */}
                    <div className="mt-6 space-y-4">
                      {result.steps.map((step) => (
                        <div
                          key={step.order}
                          className="p-5 rounded-2xl border border-line bg-paper-2 hover:border-amber-400/50 transition-all group"
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div className="flex items-start gap-3">
                              <span className="w-8 h-8 rounded-xl bg-amber-500 text-navy-950 font-black text-sm grid place-items-center shrink-0 shadow-xs">
                                {step.order}
                              </span>
                              <div>
                                <h4 className="text-base font-bold text-ink group-hover:text-amber-600 transition-colors">
                                  {step.title}
                                </h4>
                                <p className="text-sm text-ink-2 mt-1 leading-relaxed">
                                  {step.body}
                                </p>
                              </div>
                            </div>

                            {step.fee_display && (
                              <span className="text-xs font-bold px-3 py-1 rounded-lg bg-amber-500/10 text-amber-600 border border-amber-500/20 shrink-0">
                                {step.fee_display}
                              </span>
                            )}
                          </div>

                          {/* Documents Required */}
                          {step.documents && step.documents.length > 0 && (
                            <div className="mt-4 pt-3 border-t border-line/60 flex flex-wrap items-center gap-2">
                              <span className="text-[11px] font-extrabold uppercase tracking-wider text-ink-3">
                                Required Documents:
                              </span>
                              {step.documents.map((doc) => (
                                <span
                                  key={doc}
                                  className="text-xs font-medium px-2.5 py-0.5 rounded-md bg-paper border border-line text-ink-2"
                                >
                                  {doc}
                                </span>
                              ))}
                            </div>
                          )}

                          {/* Warning callout */}
                          {step.warning && (
                            <div className="mt-3 p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs font-medium text-amber-800 dark:text-amber-300 flex items-start gap-2">
                              <AlertTriangle size={15} className="text-amber-500 shrink-0 mt-0.5" />
                              <span>{step.warning}</span>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </section>
          )}
        </div>

        {/* ── Institutional Identity — About GIC Section ── */}
        <section className="py-20 bg-paper-2 border-t border-line" aria-labelledby="about-title">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <span className="inline-block text-[11px] uppercase tracking-widest font-extrabold text-amber-600 bg-amber-500/10 border border-amber-500/20 px-3.5 py-1.5 rounded-full mb-4">
              Institutional Identity
            </span>
            <h2 id="about-title" className="text-3xl sm:text-4xl font-extrabold tracking-tight text-ink mb-3">
              About GIC
            </h2>
            <p className="text-base text-ink-2 max-w-2xl leading-relaxed mb-10">
              Government Information Centre — Your trusted gateway to government services and information
            </p>

            {/* Mission & Vision row */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-12">
              <div className="bg-paper border border-line rounded-2xl p-6 sm:p-8 shadow-sm hover:border-amber-400/50 hover:-translate-y-1 transition-all duration-200">
                <div className="w-12 h-12 rounded-xl grid place-items-center bg-gradient-to-br from-amber-50 to-amber-100 dark:from-amber-500/20 dark:to-amber-500/5 text-amber-600 border border-amber-500/20 mb-5">
                  <Target size={24} />
                </div>
                <h3 className="text-xl font-bold text-ink mb-2">Our Mission</h3>
                <p className="text-sm text-ink-2 leading-relaxed">
                  To provide accessible, reliable, and comprehensive government information and services
                  to all citizens, ensuring transparency and efficient service delivery across all
                  government agencies.
                </p>
              </div>

              <div className="bg-paper border border-line rounded-2xl p-6 sm:p-8 shadow-sm hover:border-amber-400/50 hover:-translate-y-1 transition-all duration-200">
                <div className="w-12 h-12 rounded-xl grid place-items-center bg-gradient-to-br from-amber-50 to-amber-100 dark:from-amber-500/20 dark:to-amber-500/5 text-amber-600 border border-amber-500/20 mb-5">
                  <Eye size={24} />
                </div>
                <h3 className="text-xl font-bold text-ink mb-2">Our Vision</h3>
                <p className="text-sm text-ink-2 leading-relaxed">
                  A digital-first government platform that empowers citizens with instant access to
                  services, information, and support from anywhere, anytime.
                </p>
              </div>
            </div>

            {/* Core Directive Cards */}
            <div className="text-center mb-6">
              <span className="text-xs uppercase tracking-widest font-extrabold text-ink-3">
                Core Directives
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 mb-12">
              {CORE_VALUES.map(({ icon: Icon, title, desc }) => (
                <div
                  key={title}
                  className="bg-paper border border-line rounded-2xl p-6 text-center shadow-sm hover:border-amber-400/50 hover:-translate-y-1 transition-all duration-200 group"
                >
                  <div className="w-12 h-12 rounded-full grid place-items-center bg-navy-900 text-amber-400 mx-auto mb-4 group-hover:scale-110 transition-transform shadow-xs">
                    <Icon size={22} />
                  </div>
                  <h4 className="text-base font-bold text-ink mb-1">{title}</h4>
                  <p className="text-xs text-ink-2 leading-relaxed">{desc}</p>
                </div>
              ))}
            </div>

            {/* Institutional Collaborations */}
            <CollabStrip />
          </div>
        </section>

        {/* ── E-Services Grid ── */}
        <ServicesGrid />

        {/* ── Citizen Help & Support ── */}
        <GetInTouch />
      </main>

      {/* ── Site Footer ── */}
      <ContactSection />
    </div>
  );
}
