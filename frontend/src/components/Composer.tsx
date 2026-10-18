import { useRef, useState } from "react";
import { ArrowUp, Mic, Plus, X, FileText, Loader2 } from "lucide-react";

interface Attachment {
  id: string;
  name: string;
  size: number;
}

export default function Composer({
  value,
  onChange,
  onSubmit,
  busy,
  autoFocus = false,
  placeholder = "Ask about any government service… e.g. How to renew passport",
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  busy: boolean;
  autoFocus?: boolean;
  placeholder?: string;
}) {
  const taRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [isListening, setIsListening] = useState(false);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!busy && value.trim()) {
        onSubmit();
      }
    }
  }

  function handleGrow(el: HTMLTextAreaElement) {
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }

  function handlePickFiles(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) {
      const newAttachments = files.map((f) => ({
        id: `${f.name}-${Date.now()}-${f.size}`,
        name: f.name,
        size: f.size,
      }));
      setAttachments((prev) => [...prev, ...newAttachments]);
    }
    e.target.value = "";
  }

  function removeAttachment(id: string) {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  }

  function toggleVoice() {
    setIsListening((prev) => !prev);
  }

  return (
    <div className="w-full max-w-2xl mx-auto">
      {/* Attachment Chips */}
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2 px-1">
          {attachments.map((f) => (
            <span
              key={f.id}
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium bg-white/10 text-slate-200 border border-white/20 backdrop-blur-md animate-fadeIn"
            >
              <FileText size={13} className="text-amber-400" />
              <span className="max-w-[140px] truncate">{f.name}</span>
              <button
                type="button"
                onClick={() => removeAttachment(f.id)}
                className="text-slate-400 hover:text-white transition-colors cursor-pointer border-none bg-transparent p-0"
                aria-label={`Remove ${f.name}`}
              >
                <X size={12} />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Main Composer Box */}
      <div className="relative flex items-center bg-white dark:bg-navy-800/95 border-2 border-white/20 dark:border-white/10 focus-within:border-amber-400 dark:focus-within:border-amber-400 rounded-2xl shadow-xl shadow-black/20 p-2 transition-all duration-200 backdrop-blur-xl">
        {/* Attachment button */}
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          title="Attach document or ID scan"
          aria-label="Attach document"
          className="w-10 h-10 rounded-xl grid place-items-center text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/10 transition-all cursor-pointer border-none bg-transparent shrink-0"
        >
          <Plus size={20} />
        </button>
        <input
          ref={fileRef}
          type="file"
          multiple
          hidden
          onChange={handlePickFiles}
          accept=".pdf,.jpg,.jpeg,.png"
        />

        {/* Text input */}
        <textarea
          ref={taRef}
          rows={1}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            handleGrow(e.target);
          }}
          onKeyDown={handleKeyDown}
          autoFocus={autoFocus}
          placeholder={placeholder}
          aria-label="Ask about government services"
          className="flex-1 min-w-0 bg-transparent px-3 py-2 text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-slate-400 text-sm sm:text-base outline-none resize-none max-h-40 leading-relaxed font-sans"
        />

        {/* Voice toggle button */}
        <button
          type="button"
          onClick={toggleVoice}
          title={isListening ? "Listening... click to stop" : "Voice input mode"}
          aria-label="Voice input"
          className={`w-10 h-10 rounded-xl grid place-items-center transition-all cursor-pointer border-none shrink-0 ${
            isListening
              ? "bg-red-500 text-white animate-pulse"
              : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/10 bg-transparent"
          }`}
        >
          <Mic size={19} />
        </button>

        {/* Send button */}
        <button
          type="button"
          onClick={onSubmit}
          disabled={busy || !value.trim()}
          aria-label="Ask HelaGuide"
          className="w-11 h-11 rounded-xl bg-amber-500 hover:bg-amber-400 active:scale-95 text-navy-950 font-bold grid place-items-center transition-all disabled:opacity-40 disabled:hover:bg-amber-500 disabled:cursor-not-allowed cursor-pointer border-none shadow-md shadow-amber-500/20 shrink-0 ml-1"
        >
          {busy ? (
            <Loader2 size={19} className="animate-spin text-navy-950" />
          ) : (
            <ArrowUp size={20} strokeWidth={2.6} />
          )}
        </button>
      </div>

      {/* Voice active notice */}
      {isListening && (
        <div className="mt-2 text-center text-xs font-semibold text-amber-400 animate-pulse flex items-center justify-center gap-2">
          <span className="w-2 h-2 rounded-full bg-red-500" />
          Voice assist mode active — speak your query in English, Sinhala, or Tamil...
        </div>
      )}
    </div>
  );
}
