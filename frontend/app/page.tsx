import Image from "next/image";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Logo } from "@/components/ui";
import { Evidence } from "@/components/Evidence";

const SOURCES = [
  { name: "Document", text: "The QR on the card is signed by the issuer. We check the signature, then compare the QR, the printed text and the form." },
  { name: "Face and liveness", text: "The selfie must match the card and the issuer's photo, follow two random challenges, and come from a real camera." },
  { name: "Behaviour", text: "How the form was filled: typing rhythm, pasting, speed, and how many applications came from the same device." },
  { name: "Registries", text: "Identity, tax, telecom, KYC and credit records. Synthetic identities look clean on paper but have no history." },
  { name: "Identity graph", text: "Every application is linked to earlier ones that share a face, device, phone or email pattern. Rings appear as clusters." },
];

export default function Home() {
  return (
    <div className="min-h-[100dvh]">
      <header className="border-b border-line bg-panel">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Logo />
          <nav className="flex items-center gap-2">
            <Link href="/dashboard" className="btn border-transparent bg-transparent hover:bg-bg-2">Analyst console</Link>
            <Link href="/kyc" className="btn btn-primary">Start verification</Link>
          </nav>
        </div>
      </header>

      <main>
        <section className="mx-auto grid max-w-6xl items-center gap-12 px-6 pb-16 pt-16 lg:grid-cols-[1.15fr_1fr] lg:pt-20">
          <div>
            <h1 className="max-w-2xl text-4xl font-semibold leading-[1.12] tracking-tight lg:text-[42px]">
              Every check passes alone. The fraud shows up when you compare them.
            </h1>
            <p className="mt-5 max-w-lg text-lg leading-relaxed text-muted">
              TrueID Shield cross-checks documents, faces, behaviour, registries and past applications to catch synthetic identities.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/kyc" className="btn btn-primary px-5 py-2.5 text-[15px]">Start verification <ArrowRight className="size-4" /></Link>
              <Link href="/dashboard/metrics" className="btn px-5 py-2.5 text-[15px]">See the evaluation</Link>
            </div>
          </div>
          <figure>
            <Image src="/specimen-card.png" alt="Specimen national identity card with an issuer-signed QR code" width={1000} height={630}
              priority className="w-full rounded-xl border border-line shadow-[0_12px_32px_-12px_rgba(21,24,29,0.18)]" />
            <figcaption className="mt-3 text-sm text-dim">
              The QR carries the issuer&apos;s digital signature. Editing the printed date of birth breaks the match, however clean the edit looks.
            </figcaption>
          </figure>
        </section>

        <section className="border-y border-line bg-panel">
          <div className="mx-auto grid max-w-6xl gap-10 px-6 py-16 lg:grid-cols-[1fr_1.6fr]">
            <div>
              <h2 className="text-2xl font-semibold tracking-tight">Five independent sources, one decision</h2>
              <p className="mt-3 leading-relaxed text-muted">
                At ICCV 2025, the best forgery detectors scored at chance on a carefully edited date of birth.
                A single check can be beaten. Five checks that must agree are much harder to fool.
              </p>
            </div>
            <dl className="grid gap-x-10 gap-y-7 sm:grid-cols-2">
              {SOURCES.map((s) => (
                <div key={s.name}>
                  <dt className="font-semibold">{s.name}</dt>
                  <dd className="mt-1.5 text-sm leading-relaxed text-muted">{s.text}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-6 py-16">
          <h2 className="text-2xl font-semibold tracking-tight">Measured on held-out data, then attacked</h2>
          <p className="mt-3 max-w-2xl leading-relaxed text-muted">
            Trained on the first 20 days of applications and tested on the last 10, including genuine people who look unusual:
            families sharing a phone, students on one hostel network, names written differently.
          </p>
          <Evidence />
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap justify-between gap-3 px-6 py-6 text-sm text-dim">
          <span>Hacksploit 2026, problem statement 3: synthetic identity fraud in automated KYC.</span>
          <span>The language model writes explanations. It never makes the decision.</span>
        </div>
      </footer>
    </div>
  );
}
