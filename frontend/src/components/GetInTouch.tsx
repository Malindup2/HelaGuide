import { useState } from 'react';
import { Phone, Mail, MapPin, Send, Clock, ExternalLink, CheckCircle2, MessageSquare, Copy, Check } from 'lucide-react';

export default function GetInTouch() {
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [copiedNumber, setCopiedNumber] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      setSubmitted(true);
    }, 800);
  };

  const handleCopyHotline = () => {
    navigator.clipboard.writeText('1919');
    setCopiedNumber(true);
    setTimeout(() => setCopiedNumber(false), 2000);
  };

  return (
    <section className="py-20 bg-paper-2 border-t border-line relative overflow-hidden" aria-labelledby="contact-title">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        
        {/* Section Header */}
        <div className="mb-14 max-w-2xl">
          <span className="inline-flex items-center gap-2 text-[calc(11px*var(--text-scale))] uppercase tracking-widest font-extrabold text-amber-600 bg-amber-500/10 border border-amber-500/20 px-3.5 py-1.5 rounded-full mb-3 ">
            <span className="w-2 h-2 rounded-full bg-amber-500 animate-ping" />
            Citizen Help & Support Portal
          </span>
          <h2 id="contact-title" className="text-3xl sm:text-4xl font-extrabold tracking-tight text-ink">
            Get in Touch with Official Support
          </h2>
          <p className="text-base text-ink-2 mt-2 leading-relaxed">
            Have questions regarding government workflows or require assistance? Reach out to our dedicated 24/7 support channels or visit our Colombo headquarters.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          
          {/* Left Column: Direct Channels (5 cols) */}
          <div className="lg:col-span-5 space-y-4">
            <span className="text-xs uppercase tracking-widest font-extrabold text-ink-3 block mb-2">
              Direct Contact Channels
            </span>

            {/* Hotline 1919 Card */}
            <div className="bg-paper border border-line rounded-2xl p-6 shadow-sm hover:border-amber-400/50 transition-all duration-200 group">
              <div className="flex items-start justify-between">
                <div className="flex gap-4">
                  <div className="w-12 h-12 rounded-xl grid place-items-center bg-amber-500/10 text-amber-600  border border-amber-500/20 group-hover:scale-105 transition-transform shrink-0">
                    <Phone size={22} />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-ink mb-0.5">Call 1919 Hotline</h3>
                    <span className="text-[11px] font-extrabold uppercase tracking-wider text-ink-3 block">24/7 CITIZEN TOLL-FREE</span>
                  </div>
                </div>
              </div>

              <div className="mt-4 pt-4 border-t border-line/60 flex items-center justify-between">
                <strong className="text-3xl font-black text-ink tracking-tight">1919</strong>
                <button
                  type="button"
                  onClick={handleCopyHotline}
                  className="inline-flex items-center gap-1.5 text-xs font-bold text-amber-600  hover:text-amber-700 bg-amber-500/10 hover:bg-amber-500/20 px-3 py-1.5 rounded-lg transition-all cursor-pointer border-none"
                >
                  {copiedNumber ? <Check size={14} className="text-emerald-500" /> : <Copy size={14} />}
                  <span>{copiedNumber ? 'Copied!' : 'Copy Hotline'}</span>
                </button>
              </div>
            </div>

            {/* Email Support Card */}
            <div className="bg-paper border border-line rounded-2xl p-6 shadow-sm hover:border-amber-400/50 transition-all duration-200 group">
              <div className="flex items-start justify-between">
                <div className="flex gap-4">
                  <div className="w-12 h-12 rounded-xl grid place-items-center bg-amber-500/10 text-amber-600  border border-amber-500/20 group-hover:scale-105 transition-transform shrink-0">
                    <Mail size={22} />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-ink mb-0.5">Email Support</h3>
                    <span className="text-[11px] font-extrabold uppercase tracking-wider text-ink-3 block">GENERAL INQUIRIES & GUIDANCE</span>
                  </div>
                </div>
                <span className="text-[10px] font-extrabold text-amber-600 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-md  shrink-0">
                  ACTIVE 24/7
                </span>
              </div>

              <div className="mt-4 pt-4 border-t border-line/60 flex items-center justify-between">
                <a
                  href="mailto:info@gic.gov.lk"
                  className="text-lg font-bold text-amber-600  hover:underline tracking-tight"
                >
                  info@gic.gov.lk
                </a>
                <span className="text-xs text-ink-3 font-medium">Official Inbox</span>
              </div>
            </div>

            {/* Visit Headquarters Map Card */}
            <div className="bg-paper border border-line rounded-2xl p-6 shadow-sm hover:border-amber-400/50 transition-all duration-200">
              <div className="flex items-center gap-4 mb-3">
                <div className="w-12 h-12 rounded-xl grid place-items-center bg-amber-500/10 text-amber-600  border border-amber-500/20 shrink-0">
                  <MapPin size={22} />
                </div>
                <div>
                  <h3 className="text-base font-bold text-ink mb-0.5">Visit Our Headquarters</h3>
                  <span className="text-[11px] font-extrabold uppercase tracking-wider text-ink-3 block">COLOMBO 1, SRI LANKA</span>
                </div>
              </div>

              <p className="text-xs text-ink-2 leading-relaxed mb-3">
                Presidential Secretariat, Galle Face Center Road, Colombo 1, Sri Lanka.
              </p>

              <div className="flex items-center gap-2 text-xs text-ink-3 font-medium mb-4">
                <Clock size={14} className="text-amber-500 shrink-0" />
                <span>Mon – Fri: 8:30 AM – 4:15 PM</span>
              </div>

              {/* Embedded Map */}
              <div className="w-full rounded-xl overflow-hidden ring-1 ring-line shadow-inner bg-line">
                <iframe
                  title="GIC Headquarters Map"
                  width="100%"
                  height="160"
                  src="https://www.openstreetmap.org/export/embed.html?bbox=79.8400%2C6.9200%2C79.8500%2C6.9300&amp;layer=mapnik&amp;marker=6.9271%2C79.8440"
                  className="border-none block"
                />
              </div>

              <a
                href="https://maps.google.com/?q=Presidential+Secretariat+Colombo+Sri+Lanka"
                target="_blank"
                rel="noreferrer noopener"
                className="mt-3 inline-flex items-center gap-1.5 text-xs font-bold text-amber-600  hover:underline"
              >
                <span>Open in Google Maps</span>
                <ExternalLink size={13} />
              </a>
            </div>

          </div>

          {/* Right Column: Interactive Message Form (7 cols) */}
          <div className="lg:col-span-7 bg-paper border border-line rounded-2xl p-6 sm:p-8 shadow-sm relative">
            
            {/* Header */}
            <div className="flex items-center justify-between pb-6 mb-6 border-b border-line">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl grid place-items-center bg-navy-800 text-amber-400  ">
                  <MessageSquare size={20} />
                </div>
                <div>
                  <h3 className="text-xl font-bold text-ink">Send an Official Inquiry</h3>
                  <p className="text-xs text-ink-3">Guaranteed response within 1 business day</p>
                </div>
              </div>
            </div>

            {submitted ? (
              <div className="py-12 text-center space-y-4">
                <div className="w-16 h-16 rounded-full bg-emerald-500/10 text-emerald-500 grid place-items-center mx-auto border border-emerald-500/20">
                  <CheckCircle2 size={36} />
                </div>
                <h4 className="text-2xl font-extrabold text-ink">Inquiry Submitted Successfully</h4>
                <p className="text-sm text-ink-2 max-w-md mx-auto leading-relaxed">
                  Thank you for contacting the Government Information Centre. Your ticket reference has been logged and an official response will be sent to your email shortly.
                </p>
                <button
                  onClick={() => setSubmitted(false)}
                  className="mt-4 inline-flex items-center justify-center px-6 py-2.5 rounded-xl font-bold text-xs uppercase tracking-wider text-navy-950 bg-amber-500 hover:bg-amber-400 transition-all cursor-pointer border-none shadow-sm"
                >
                  Send Another Message
                </button>
              </div>
            ) : (
              <form className="space-y-5" onSubmit={handleSubmit}>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                  <label className="block">
                    <span className="block text-xs font-bold text-ink-2 uppercase tracking-wider mb-2">Full Name *</span>
                    <input
                      required
                      type="text"
                      placeholder="e.g. K. A. Perera"
                      className="w-full h-11 px-4 rounded-xl border border-line bg-paper-2 text-ink text-sm placeholder:text-ink-3 focus:outline-none focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20 transition-all"
                    />
                  </label>

                  <label className="block">
                    <span className="block text-xs font-bold text-ink-2 uppercase tracking-wider mb-2">Email Address *</span>
                    <input
                      required
                      type="email"
                      placeholder="perera@example.com"
                      className="w-full h-11 px-4 rounded-xl border border-line bg-paper-2 text-ink text-sm placeholder:text-ink-3 focus:outline-none focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20 transition-all"
                    />
                  </label>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                  <label className="block">
                    <span className="block text-xs font-bold text-ink-2 uppercase tracking-wider mb-2">Contact Phone / NIC (Optional)</span>
                    <input
                      type="text"
                      placeholder="0771234567 or 1990..."
                      className="w-full h-11 px-4 rounded-xl border border-line bg-paper-2 text-ink text-sm placeholder:text-ink-3 focus:outline-none focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20 transition-all"
                    />
                  </label>

                  <label className="block">
                    <span className="block text-xs font-bold text-ink-2 uppercase tracking-wider mb-2">Inquiry Category *</span>
                    <select
                      required
                      className="w-full h-11 px-4 rounded-xl border border-line bg-paper-2 text-ink text-sm focus:outline-none focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20 transition-all cursor-pointer appearance-auto"
                    >
                      <option value="">Select topic...</option>
                      <option value="general">General Government Inquiry</option>
                      <option value="workflow">Service Workflow & Requirements</option>
                      <option value="complaint">Official Complaint / Grievance</option>
                      <option value="tech">Portal Technical Issue</option>
                      <option value="feedback">Feedback & Suggestions</option>
                    </select>
                  </label>
                </div>

                <label className="block">
                  <span className="block text-xs font-bold text-ink-2 uppercase tracking-wider mb-2">Inquiry Details *</span>
                  <textarea
                    required
                    rows={5}
                    placeholder="Please describe the government service, office, or document guidance you need help with..."
                    className="w-full p-4 rounded-xl border border-line bg-paper-2 text-ink text-sm placeholder:text-ink-3 focus:outline-none focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20 transition-all resize-y"
                  />
                </label>

                <div className="pt-2">
                  <button
                    disabled={loading}
                    type="submit"
                    className="w-full h-12 rounded-xl font-extrabold text-sm uppercase tracking-wider text-navy-950 bg-amber-500 hover:bg-amber-400 active:scale-[0.99] transition-all cursor-pointer border-none shadow-md flex items-center justify-center gap-2 disabled:opacity-70"
                  >
                    {loading ? (
                      <span className="w-5 h-5 border-2 border-navy-950 border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <>
                        <Send size={16} />
                        <span>Submit Official Inquiry</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            )}

          </div>

        </div>

      </div>
    </section>
  );
}
