import Link from "next/link";
import { Camera, FileCheck2, PenLine, Smartphone } from "lucide-react";
import { Header } from "@/components/Brand";

const NEED = [
  { icon: Smartphone, title: "Mobile linked to your national ID", text: "We send OTPs to it for DigiLocker and eSign." },
  { icon: FileCheck2, title: "Your PAN", text: "Checked against Income Tax records as you type it." },
  { icon: Camera, title: "A camera and good light", text: "For a short live selfie and a photo of your ID card." },
  { icon: PenLine, title: "About 10 minutes", text: "You can't save halfway, so finish in one sitting." },
];

export default function Home() {
  return (
    <>
      <Header right={<Link href="/ops" className="hover:text-ink">Bank operations</Link>} />
      <main className="mx-auto grid max-w-6xl gap-12 px-4 py-14 sm:px-6 md:grid-cols-[1.15fr_1fr] md:py-20">
        <section>
          <h1 className="max-w-[16ch] text-[2.6rem] font-semibold leading-[1.05] tracking-[-0.03em] sm:text-[3.4rem]">
            Open a savings account without visiting a branch.
          </h1>
          <p className="mt-5 max-w-[52ch] text-lg leading-relaxed text-muted">
            Full KYC, done online. You verify your mobile, PAN and national ID, take a live selfie and eSign.
            Your account number is ready when you finish.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-4">
            <Link href="/onboard" className="btn btn-primary px-6 py-3.5 text-base">Open an account</Link>
            <span className="text-sm text-muted">Zero balance for the first year. 3.5% interest.</span>
          </div>
        </section>
        <section className="card p-6 sm:p-8">
          <h2 className="text-lg font-semibold">What you need</h2>
          <ul className="mt-5 space-y-5">
            {NEED.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-4">
                <span className="grid size-10 shrink-0 place-items-center rounded-full bg-mist text-spruce"><Icon className="size-5" /></span>
                <div>
                  <div className="font-medium">{title}</div>
                  <div className="text-sm text-muted">{text}</div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </main>
      <footer className="mx-auto max-w-6xl px-4 pb-10 text-xs text-faint sm:px-6">
        Northstar Bank is a fictional bank used to demonstrate TrueID Shield. Identity checks are simulated.
      </footer>
    </>
  );
}
