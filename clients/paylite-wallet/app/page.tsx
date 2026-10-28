import Link from "next/link";
import { Logo } from "@/components/Brand";

export default function Home() {
  return (
    <div className="flex min-h-dvh flex-col">
      <section className="bg-plum text-white">
        <div className="mx-auto max-w-5xl px-4 pb-16 pt-5 sm:px-6">
          <nav className="flex items-center justify-between">
            <Logo light />
            <Link href="/ops" className="text-sm text-white/60 hover:text-white">Operations</Link>
          </nav>
          <div className="mt-12 grid items-center gap-12 md:mt-16 md:grid-cols-[1.1fr_1fr]">
            <div>
              <h1 className="text-[2.7rem] font-bold leading-[1] tracking-[-0.035em] sm:text-[3.6rem]">
                A wallet in two minutes. Just your phone.
              </h1>
              <p className="mt-5 max-w-[42ch] text-lg text-white/75">
                Pay at any UPI QR, recharge, and split bills. Verify your number, add your ID, and you&apos;re in.
              </p>
              <Link href="/start" className="btn btn-mango mt-8 px-7 py-4 text-[1.05rem]">Create my wallet</Link>
            </div>
            <WalletCard />
          </div>
        </div>
      </section>
      <section className="mx-auto grid w-full max-w-5xl gap-8 px-4 py-14 sm:grid-cols-3 sm:px-6">
        {[
          ["No paperwork", "Type your details and upload a photo of your ID. No branch, no video call."],
          ["₹10,000 a month to start", "That's the limit for wallets opened with minimum KYC. Raise it with full KYC later."],
          ["Free UPI payments", "No fee on any payment, on any app's QR code."],
        ].map(([t, d]) => (
          <div key={t}>
            <h2 className="text-lg font-semibold">{t}</h2>
            <p className="mt-1.5 text-muted">{d}</p>
          </div>
        ))}
      </section>
      <footer className="mx-auto mt-auto w-full max-w-5xl px-4 pb-8 text-xs text-faint sm:px-6">
        PayLite is a fictional wallet used to demonstrate TrueID Shield. Identity checks are simulated.
      </footer>
    </div>
  );
}

function WalletCard() {
  return (
    <div aria-hidden className="relative mx-auto w-full max-w-sm">
      <div className="absolute -right-3 top-6 h-full w-full rotate-6 rounded-[28px] bg-mango/90" />
      <div className="relative rounded-[28px] bg-white p-6 text-ink shadow-[0_30px_60px_-25px_rgba(10,0,30,.6)]">
        <div className="flex items-center justify-between text-sm text-muted"><span>PayLite balance</span><span>Riya K.</span></div>
        <div className="mt-2 text-[2.6rem] font-bold tracking-[-0.03em] tabular-nums">₹2,450.00</div>
        <div className="mt-6 space-y-3 text-sm">
          {[["Chai Point, Panaji", "−₹60"], ["Mobile recharge", "−₹239"], ["From Arjun", "+₹500"]].map(([a, b]) => (
            <div key={a} className="flex justify-between border-t border-line pt-3"><span>{a}</span><span className="tabular-nums font-medium">{b}</span></div>
          ))}
        </div>
      </div>
    </div>
  );
}
