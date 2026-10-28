import type { Metadata, Viewport } from "next";
import "@fontsource-variable/bricolage-grotesque";
import "./globals.css";

export const metadata: Metadata = {
  title: "PayLite: your wallet in two minutes",
  description: "Demo partner wallet for TrueID Shield. Fictional brand.",
};
export const viewport: Viewport = { themeColor: "#2b1747" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-IN">
      <body className="min-h-dvh">{children}</body>
    </html>
  );
}
