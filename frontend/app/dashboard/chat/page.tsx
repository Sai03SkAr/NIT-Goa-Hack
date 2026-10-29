"use client";
import { BarChart3, FileSearch, GraduationCap, Network, RotateCcw, ShieldCheck } from "lucide-react";
import { PageHeader, Section } from "@/components/ui";
import { Composer, Conversation, useAssistant } from "@/components/Assistant";

const CAN = [
  { icon: BarChart3, title: "Read the analytics", text: "How fraud is trending, the most common signals this week, how many cases wait for review." },
  { icon: FileSearch, title: "Explain a case", text: "Why an application was flagged, which checks failed, what to verify before deciding. Mention its ID." },
  { icon: Network, title: "Follow the links", text: "Which applications share a face, device or typing rhythm, and how many names a ring uses." },
  { icon: GraduationCap, title: "Explain the terms", text: "Recall, false alarms, ROC-AUC, PSI, drift, liveness, the consortium. Ask what any number means." },
];

/** The full-page Investigator: the same conversation as the floating "Ask TrueID" panel, with room to dig in. */
export default function Investigator() {
  const a = useAssistant();
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Operations" title="Investigator"
        right={!!a.msgs.length && <button className="btn min-h-11" onClick={a.clear}><RotateCcw className="size-4" />New conversation</button>}>
        Your analytics assistant. It answers from the live database and the evaluation files, keeps the conversation you started in the
        floating panel, and can explain but never change a decision.
      </PageHeader>
      <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <section className="panel flex min-h-[60dvh] flex-col">
          <div className="flex-1 p-5"><Conversation a={a} large /></div>
          <div className="sticky bottom-0 rounded-b-2xl border-t border-line bg-panel p-3"><Composer a={a} autoFocus /></div>
        </section>
        <aside className="space-y-5 xl:sticky xl:top-6">
          <Section title="What it can do">
            <ul className="space-y-4">
              {CAN.map((c) => (
                <li key={c.title} className="flex gap-3">
                  <c.icon className="mt-0.5 size-4 shrink-0 text-brand" />
                  <div><div className="text-sm font-medium">{c.title}</div><div className="text-[13px] leading-snug text-muted">{c.text}</div></div>
                </li>
              ))}
            </ul>
          </Section>
          <Section title="How answers are made">
            <p className="flex gap-2 text-[13px] leading-relaxed text-muted"><ShieldCheck className="mt-0.5 size-4 shrink-0 text-approve" />
              Facts are looked up first (totals, the case record, the graph, evaluation, the learning loop). With an AI key (Groq or Grok) the
              wording is natural; an answer that mentions an ID or code not in the facts is thrown away. Without a key, answers are built from the facts directly.</p>
          </Section>
        </aside>
      </div>
    </div>
  );
}
