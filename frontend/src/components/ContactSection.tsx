import { useState } from 'react';
import { MapPin, Phone, Mail, Shield, Facebook, Instagram, Linkedin, Youtube } from 'lucide-react';

const QUICK_LINKS = [
  { label: 'Home', href: '#' },
  { label: 'About', href: '#' },
  { label: 'Services', href: '#' },
  { label: 'Divisions', href: '#' },
  { label: 'News & Updates', href: '#' },
  { label: 'Contact', href: '#contact' },
];

const POPULAR_SERVICES = [
  'Birth Registration',
  'Passport Services',
  'Driving License',
  'Business Registration',
  'Pension Information',
];

const SOCIALS = [
  { Icon: Facebook, label: 'Facebook', href: '#' },
  { Icon: Instagram, label: 'Instagram', href: '#' },
  { Icon: Linkedin, label: 'LinkedIn', href: '#' },
  { Icon: Youtube, label: 'YouTube', href: '#' },
];

export default function ContactSection() {
  const [logoFailed, setLogoFailed] = useState(false);

  return (
    <footer className="bg-navy-900 border-t-4 border-amber-500 text-slate-300 font-sans" aria-label="Site footer">
      {/* ── Main footer content ── */}
      <div className="py-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-12">
          {/* Column 1 — Brand */}
          <div className="flex flex-col gap-6">
            <div className="flex items-center gap-4">
              {!logoFailed ? (
                <img
                  className="h-16 w-auto drop-shadow-md"
                  src="/logos/collab1.png"
                  alt="Government Information Centre"
                  onError={() => setLogoFailed(true)}
                />
              ) : (
                <span className="w-14 h-14 bg-navy-800 rounded-lg flex items-center justify-center font-bold text-amber-500 tracking-wider ring-1 ring-white/10">
                  GIC
                </span>
              )}
              <div className="flex flex-col justify-center">
                <strong className="font-extrabold text-2xl text-white tracking-tight leading-none">GIC</strong>
                <span className="text-[11px] font-bold text-amber-500 uppercase tracking-[0.2em] mt-1">SRI LANKA</span>
              </div>
            </div>

            <p className="text-sm leading-relaxed text-slate-400">
              The official Government Information Centre of Sri Lanka, providing
              seamless access to public services and information for all citizens.
            </p>

            <div className="flex gap-3">
              {SOCIALS.map(({ Icon, label, href }) => (
                <a
                  key={label}
                  className="w-10 h-10 rounded-full bg-white/5 flex items-center justify-center text-slate-300 hover:bg-amber-500 hover:text-navy-900 transition-colors"
                  href={href}
                  aria-label={label}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  <Icon size={18} />
                </a>
              ))}
            </div>
          </div>

          {/* Column 2 — Quick links */}
          <div className="flex flex-col">
            <h3 className="text-sm font-bold text-white mb-6 flex items-center gap-3 uppercase tracking-wider">
              <span className="w-2 h-2 bg-amber-500 rounded-sm" />
              Quick Links
            </h3>
            <ul className="list-none p-0 m-0 flex flex-col gap-3">
              {QUICK_LINKS.map(({ label, href }) => (
                <li key={label}>
                  <a className="text-sm text-slate-400 hover:text-amber-400 transition-colors no-underline flex items-center gap-2 hover:translate-x-1 duration-200" href={href}>{label}</a>
                </li>
              ))}
            </ul>
          </div>

          {/* Column 3 — Popular services */}
          <div className="flex flex-col">
            <h3 className="text-sm font-bold text-white mb-6 flex items-center gap-3 uppercase tracking-wider">
              <span className="w-2 h-2 bg-amber-500 rounded-sm" />
              Popular Services
            </h3>
            <ul className="list-none p-0 m-0 flex flex-col gap-3">
              {POPULAR_SERVICES.map((s) => (
                <li key={s}>
                  <a className="text-sm text-slate-400 hover:text-amber-400 transition-colors no-underline flex items-center gap-2 hover:translate-x-1 duration-200" href="#">{s}</a>
                </li>
              ))}
            </ul>
          </div>

          {/* Column 4 — Get in touch */}
          <div className="flex flex-col">
            <h3 className="text-sm font-bold text-white mb-6 flex items-center gap-3 uppercase tracking-wider">
              <span className="w-2 h-2 bg-amber-500 rounded-sm" />
              Get in Touch
            </h3>

            <div className="flex flex-col gap-5">
              <div className="flex items-start gap-4 text-sm text-slate-300 leading-relaxed">
                <span className="mt-1 text-amber-500 shrink-0">
                  <MapPin size={18} />
                </span>
                <div className="flex flex-col">
                  <span>Presidential Secretariat,</span>
                  <span>Galle Face Center Road,</span>
                  <span>Colombo 1, Sri Lanka.</span>
                </div>
              </div>

              <div className="flex items-start gap-4 text-sm text-slate-300 leading-relaxed">
                <span className="mt-1 text-amber-500 shrink-0">
                  <Phone size={18} />
                </span>
                <div>
                  <strong className="block text-2xl font-bold text-white leading-none mb-1">1919</strong>
                  <span className="text-[10px] text-amber-500 font-bold tracking-wider">
                    (24/7 GOVERNMENT HOTLINE)
                  </span>
                </div>
              </div>

              <div className="flex items-start gap-4 text-sm text-slate-300 leading-relaxed">
                <span className="mt-1 text-amber-500 shrink-0">
                  <Mail size={18} />
                </span>
                <div>
                  <a href="mailto:info@gic.gov.lk" className="text-amber-400 hover:text-white transition-colors no-underline font-medium">
                    info@gic.gov.lk
                  </a>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Bottom bar ── */}
      <div className="bg-navy-950 py-6 border-t border-white/5">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row justify-between items-center gap-6">
          <div className="flex flex-col gap-2 text-xs text-slate-500 text-center md:text-left">
            <p className="m-0">
              © {new Date().getFullYear()} Government Information Center. All
              Rights Reserved.
            </p>
            <p className="flex items-center justify-center md:justify-start gap-2 text-amber-500/80 m-0">
              <Shield size={10} />
              Research Prototype · SLIIT IT4010 — This is a research demonstration, not an official government service.
            </p>
          </div>

          <div className="flex flex-wrap justify-center gap-6 text-xs font-medium text-slate-400">
            <a className="hover:text-amber-400 transition-colors no-underline text-inherit" href="#">Privacy Policy</a>
            <a className="hover:text-amber-400 transition-colors no-underline text-inherit" href="#">Terms of Service</a>
            <a className="hover:text-amber-400 transition-colors no-underline text-inherit" href="#">Accessibility</a>
          </div>
        </div>
      </div>
    </footer>
  );
}
