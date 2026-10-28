"use client";
import { useState } from "react";
import Link from "next/link";
import { Send, Wrench } from "lucide-react";
import { Section } from "@/components/ui";
import { post } from "@/lib/api";

type Msg = { role: "user" | "assistant"; text: string; source?: string; tools?: { tool: string; args: Record<string, unknown>; result: unknown }[] };

const EXAMPLES = ["Why is A00123 linked to other applications?", "Explain bio_sim_card_registry", "Compare A00010 and A00011"];

export default function Chat() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);

  async function ask(question: string) {
    if (!question.trim()) return;
    setMsgs((m) => [...m, { role: "user", text: question }]);
    setQ(""); setBusy(true);
    try {
      const r = await post<{ answer: string; source: string; tools: Msg["tools"] }>("/api/chat", { question });
      setMsgs((m) => [...m, { role: "assistant", text: r.answer, source: r.source, tools: r.tools }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", text: `Error: ${e}` }]);
    } finally { setBusy(false); }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Investigator</h1>
        <p className="mt-1 text-sm text-muted">Ask about applications by ID or about model features. Answers come only from case records and the identity graph; the assistant cannot change a decision.</p>
      </div>
      <Section title="Conversation">
        <div className="space-y-4">
          {!msgs.length && (
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((e) => <button key={e} className="chip hover:text-fg" onClick={() => ask(e)}>{e}</button>)}
            </div>
          )}
          {msgs.map((m, i) => (
            <div key={i} className={m.role === "user" ? "ml-auto max-w-[80%] rounded-xl bg-white/[0.06] px-4 py-2.5 text-sm" : "max-w-[90%] text-sm leading-relaxed"}>
              <p>{linkIds(m.text)}</p>
              {m.role === "assistant" && m.source && <div className="mt-1 text-[11px] text-dim">answered from {m.source === "llm" ? "LLM over tool results" : "tool results (template)"}</div>}
              {!!m.tools?.length && (
                <details className="mt-2 rounded-lg border border-line p-2 text-xs text-muted">
                  <summary className="flex cursor-pointer items-center gap-1.5"><Wrench className="size-3" />{m.tools.length} tool call{m.tools.length > 1 ? "s" : ""}</summary>
                  <pre className="mono mt-2 max-h-64 overflow-auto whitespace-pre-wrap text-[11px]">{JSON.stringify(m.tools, null, 1)}</pre>
                </details>
              )}
            </div>
          ))}
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
            <input className="input" placeholder="e.g. Why are RSAB120 and RSAB121 linked?" value={q} onChange={(e) => setQ(e.target.value)} />
            <button className="btn btn-primary" disabled={busy || !q.trim()}><Send className="size-4" />{busy ? "…" : "Ask"}</button>
          </form>
        </div>
      </Section>
    </div>
  );
}

function linkIds(text: string) {
  return text.split(/\b((?:A\d{5}|L[0-9A-F]{8}|RS[0-9A-F]{4}\d+))\b/).map((part, i) =>
    i % 2 ? <Link key={i} href={`/dashboard/case/${part}`} className="mono text-brand hover:underline">{part}</Link> : part);
}
