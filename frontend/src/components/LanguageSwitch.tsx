import { useState, useEffect } from "react";
import { Moon, Sun } from "lucide-react";
import { applyTheme, getInitialTheme, type Theme } from "../lib/theme";

const LANGS = [
  { code: "si", label: "සිං" },
  { code: "ta", label: "தமி" },
  { code: "en", label: "EN" },
];

export default function LanguageSwitch({
  currentLang = "en",
  onSelectLang,
}: {
  currentLang?: string;
  onSelectLang?: (lang: string) => void;
}) {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const initial = getInitialTheme();
    setTheme(initial);
    applyTheme(initial);
  }, []);

  function toggleTheme() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    applyTheme(next);
  }

  return (
    <div className="inline-flex items-center gap-1 p-1 rounded-full border border-white/20 bg-white/5 backdrop-blur-sm">
      <div className="inline-flex items-center gap-1" role="group" aria-label="Language selection">
        {LANGS.map((l) => {
          const active = currentLang === l.code;
          return (
            <button
              key={l.code}
              type="button"
              onClick={() => onSelectLang?.(l.code)}
              className={`px-2.5 py-0.5 rounded-full text-xs font-semibold transition-all cursor-pointer border-none ${
                active
                  ? "bg-amber-500 text-navy-950 shadow-sm"
                  : "bg-transparent text-slate-300 hover:text-white hover:bg-white/10"
              }`}
            >
              {l.label}
            </button>
          );
        })}
      </div>

      <span className="w-px h-3.5 bg-white/20 mx-1" aria-hidden="true" />

      <button
        type="button"
        onClick={toggleTheme}
        aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
        title={theme === "dark" ? "Light theme" : "Dark theme"}
        className="w-7 h-6 rounded-full grid place-items-center bg-amber-500/20 text-amber-300 hover:bg-amber-500 hover:text-navy-950 transition-all cursor-pointer border-none"
      >
        {theme === "dark" ? <Sun size={13} /> : <Moon size={13} />}
      </button>
    </div>
  );
}
