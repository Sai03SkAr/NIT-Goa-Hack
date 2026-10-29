"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { ArrowUp, Database, Maximize2, RotateCcw, Sparkles, X } from "lucide-react";
import { post } from "@/lib/api";
import { readable } from "@/components/ui";

export type Turn = { role: "user" | "assistant"; text: string; source?: string; used?: string[]; page?: string;
  links?: { label: string; href: string }[]; suggestions?: string[]; error?: boolean };

const KEY = "trueid-assistant";
const SYNC = "trueid-assistant-sync";
const USED: Record<string, string> = { overview: "live totals", top_reasons_last_7_days: "this week's signals", cases: "case record",
  patterns: "fraud patterns", model_performance: "evaluation", learning_loop: "learning loop", definitions: "glossary", features: "feature docs" };
export const PAGE_SUGGESTIONS: Record<string, string[]> = {
  queue: ["How is fraud trending this week?", "What are the most common fraud signals?", "Show me the synthetic rings"],
  case: ["Why was this case flagged?", "Which applications is this one linked to?", "What should I check before deciding?"],
  graph: ["How many rings are there?", "What makes a strong link?", "Show me the synthetic rings"],
  metrics: ["How good is the model?", "Which fraud pattern is caught least?", "What is a false alarm?"],
  "attack-lab": ["Which attacks does the system resist?", "What is liveness?", "How good is the model?"],
  learning: ["What is the learning loop proposing?", "Is there any drift?", "What is PSI?"],
  chat: ["How is fraud trending this week?", "Explain the evaluation numbers", "What is the learning loop proposing?"],
};

export function pageKey(path: string) {
  if (path.startsWith("/dashboard/case")) return "case";
  for (const k of ["graph", "metrics", "attack-lab", "learning", "chat"]) if (path.startsWith(`/dashboard/${k}`)) return k;
  return "queue";
}
const PAGE_NAME: Record<string, string> = { queue: "Review queue", case: "Case", graph: "Identity graph", metrics: "Evaluation",
  "attack-lab": "Attack Lab", learning: "Learning loop", chat: "Investigator" };

/** One conversation shared by the floating panel and the Investigator page (kept for this browser tab). */
export function useAssistant() {
  const path = usePathname();
  const [msgs, setMsgs] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const caseId = path.startsWith("/dashboard/case/") ? decodeURIComponent(path.split("/")[3] ?? "") : undefined;

  useEffect(() => {
    const read = () => { try { setMsgs(JSON.parse(sessionStorage.getItem(KEY) || "[]")); } catch { setMsgs([]); } };
    read();
    window.addEventListener(SYNC, read);
    return () => window.removeEventListener(SYNC, read);
  }, []);
  const save = (m: Turn[]) => { setMsgs(m); try { sessionStorage.setItem(KEY, JSON.stringify(m.slice(-30))); } catch {} window.dispatchEvent(new Event(SYNC)); };

  const ask = useCallback(async (question: string) => {
    const q = question.trim();
    if (!q || busy) return;
    const before = msgs;
    const withQ = [...before, { role: "user" as const, text: q, page: PAGE_NAME[pageKey(path)] + (caseId ? ` ${caseId}` : "") }];
    save(withQ);
    setBusy(true);
    try {
      const r = await post<{ answer: string; source: string; used: string[]; links: Turn["links"]; suggestions: string[] }>("/api/assistant",
        { question: q, path, context_id: caseId, history: before.slice(-6).map(({ role, text }) => ({ role, text })) });
      save([...withQ, { role: "assistant", text: readable(r.answer), source: r.source, used: r.used, links: r.links, suggestions: r.suggestions }]);
    } catch (e) {
      save([...withQ, { role: "assistant", text: `I couldn't reach the TrueID backend (${e instanceof Error ? e.message : e}).`, error: true }]);
    } finally { setBusy(false); }
  }, [busy, msgs, path, caseId]);

  return { msgs, busy, ask, clear: () => save([]), path, caseId, page: pageKey(path) };
}

export function Conversation({ a, large = false }: { a: ReturnType<typeof useAssistant>; large?: boolean }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [a.msgs.length, a.busy]);
  const last = [...a.msgs].reverse().find((m) => m.role === "assistant");
  const sugg = last?.suggestions ?? PAGE_SUGGESTIONS[a.page];
  return (
    <div className={clsx("space-y-4", large ? "text-[15px]" : "text-sm")}>
      {!a.msgs.length && (
        <div className="rounded-xl bg-bg-2/70 p-4">
          <p className="font-medium">Ask about anything you see.</p>
          <p className="mt-1 text-muted">How fraud is trending, why a case was flagged, what a number or term means, or what the learning loop proposes. Answers come from the live data.</p>
        </div>
      )}
      {a.msgs.map((m, i) => m.role === "user" ? (
        <div key={i} className="flex justify-end"><div className="max-w-[85%] rounded-2xl rounded-br-md bg-ink px-3.5 py-2.5 text-white">{m.text}</div></div>
      ) : (
        <div key={i} className="max-w-[95%]">
          <div className={clsx("rounded-2xl rounded-bl-md border px-3.5 py-2.5 leading-relaxed", m.error ? "border-reject/30 text-reject" : "border-line bg-panel")}>{linkIds(m.text)}</div>
          {(!!m.links?.length || !!m.used?.length) && (
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs">
              {m.links?.map((l) => <Link key={l.href} href={l.href} className="chip text-brand hover:border-brand">{l.label}</Link>)}
              {!!m.used?.length && <span className="flex items-center gap-1 text-dim"><Database className="size-3" />{m.used.map((u) => USED[u] ?? u).join(" · ")}
                {m.source && m.source !== "template" && <> · worded by {m.source === "grok" ? "Grok" : m.source === "groq" ? "Groq" : m.source}</>}</span>}
            </div>
          )}
        </div>
      ))}
      {a.busy && <div className="flex items-center gap-2 text-dim"><Sparkles className="size-4 animate-pulse" />Looking at the data…</div>}
      {!a.busy && (
        <div className="flex flex-wrap gap-1.5">
          {sugg.map((s) => <button key={s} onClick={() => a.ask(s)} className="rounded-full border border-line-2 bg-panel px-3 py-1.5 text-left text-[13px] text-muted transition-colors hover:border-brand hover:text-brand">{s}</button>)}
        </div>
      )}
      <div ref={end} />
    </div>
  );
}

export function Composer({ a, autoFocus }: { a: ReturnType<typeof useAssistant>; autoFocus?: boolean }) {
  const [q, setQ] = useState("");
  const send = () => { if (q.trim()) { a.ask(q); setQ(""); } };
  return (
    <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex items-end gap-2 rounded-2xl border border-line-2 bg-panel p-2 focus-within:border-brand">
      <textarea aria-label="Ask TrueID" rows={1} autoFocus={autoFocus} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about the data, a case or a term"
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
        className="max-h-32 min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-dim" />
      <button aria-label="Send" disabled={!q.trim() || a.busy} className="grid size-10 shrink-0 place-items-center rounded-xl bg-ink text-white disabled:opacity-40"><ArrowUp className="size-4" /></button>
    </form>
  );
}

/** Floating "Ask TrueID" button and side panel, on every analyst page except the Investigator itself. */
export function AssistantDock() {
  const a = useAssistant();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
      if ((e.ctrlKey || e.metaKey) && e.key === "/") { e.preventDefault(); setOpen((o) => !o); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);
  if (a.page === "chat") return null;
  return (
    <>
      <button onClick={() => setOpen(true)} aria-label="Ask TrueID" title="Ask TrueID (Ctrl + /)"
        className={clsx("fixed bottom-5 right-5 z-40 flex h-12 items-center gap-2 rounded-full bg-ink pl-4 pr-5 text-white shadow-[0_10px_30px_-8px_rgba(20,22,26,0.55)] transition-all hover:-translate-y-0.5",
          open && "pointer-events-none translate-y-2 opacity-0")}>
        <Sparkles className="size-[18px] text-[#a9b1ff]" /><span className="text-sm font-medium">Ask TrueID</span>
      </button>
      <div className={clsx("fixed inset-0 z-40 bg-ink/20 transition-opacity sm:hidden", open ? "opacity-100" : "pointer-events-none opacity-0")} onClick={() => setOpen(false)} />
      <aside role="dialog" aria-label="Ask TrueID" aria-hidden={!open}
        className={clsx("fixed bottom-0 right-0 top-0 z-50 flex w-full flex-col border-l border-line bg-bg shadow-[var(--shadow-lg)] transition-transform duration-200 sm:w-[420px]",
          open ? "translate-x-0" : "pointer-events-none translate-x-full")}>
        <header className="flex items-center gap-3 border-b border-line bg-panel px-4 py-3">
          <span className="grid size-8 place-items-center rounded-lg bg-ink"><Sparkles className="size-4 text-[#a9b1ff]" /></span>
          <div className="min-w-0 flex-1">
            <div className="display text-[16px] leading-tight">Ask TrueID</div>
            <div className="truncate text-xs text-dim">Looking at: {PAGE_NAME[a.page]}{a.caseId && <span className="mono"> {a.caseId}</span>}</div>
          </div>
          {!!a.msgs.length && <button className="btn btn-ghost size-9 p-0" onClick={a.clear} aria-label="New conversation" title="New conversation"><RotateCcw className="size-4" /></button>}
          <Link href="/dashboard/chat" onClick={() => setOpen(false)} className="btn btn-ghost size-9 p-0" aria-label="Open in Investigator" title="Open in Investigator"><Maximize2 className="size-4" /></Link>
          <button className="btn btn-ghost size-9 p-0" onClick={() => setOpen(false)} aria-label="Close"><X className="size-4" /></button>
        </header>
        <div className="flex-1 overflow-y-auto px-4 py-4"><Conversation a={a} /></div>
        <div className="border-t border-line bg-panel p-3">
          {open && <Composer a={a} autoFocus />}
          <p className="mt-1.5 px-1 text-[11px] text-dim">Reads the data; never changes a decision. Ctrl + / to toggle.</p>
        </div>
      </aside>
    </>
  );
}

/** Application IDs in an answer become links to the case. */
function linkIds(text: string) {
  return text.split(/\b((?:A\d{5}|L[0-9A-F]{8}|RS[0-9A-F]{4}\d+))\b/).map((part, i) =>
    i % 2 ? <Link key={i} href={`/dashboard/case/${part}`} className="mono text-brand hover:underline">{part}</Link> : part);
}
