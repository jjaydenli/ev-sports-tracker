import type { Metadata } from "next";
import { Familjen_Grotesk, Instrument_Serif } from "next/font/google";

import { SITE_NAME } from "@/lib/board";

import "./globals.css";

const sans = Familjen_Grotesk({ subsets: ["latin"], variable: "--font-sans" });
const serif = Instrument_Serif({ subsets: ["latin"], weight: "400", variable: "--font-serif" });

export const metadata: Metadata = {
  title: SITE_NAME,
  description:
    "Each Betr pick'em prop's fair hit chance from sportsbook no-vig odds, against Betr's breakeven.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable}`}>
      <body>{children}</body>
    </html>
  );
}
