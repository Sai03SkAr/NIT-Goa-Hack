import type { Metadata } from "next";
import "@fontsource-variable/instrument-sans";
import "./globals.css";

export const metadata: Metadata = {
  title: "Northstar Bank: open a savings account",
  description: "Demo partner bank for TrueID Shield. Fictional brand.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-IN">
      <body className="min-h-dvh">{children}</body>
    </html>
  );
}
