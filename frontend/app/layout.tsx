import type { Metadata } from "next";
import { Cinzel, Familjen_Grotesk } from "next/font/google";
import localFont from "next/font/local";

import { SITE_NAME } from "@/lib/board";

import "./globals.css";

const sans = Familjen_Grotesk({ subsets: ["latin"], variable: "--font-sans" });
const serif = Cinzel({ subsets: ["latin"], weight: "600", variable: "--font-serif" });
// Familjen Medium with lower case redrawn as Bold capitals at 0.8: small caps at a set ratio,
// which browsers cannot synthesise (they fix it at ~0.69). Licence: fonts/OFL.txt.
const caps = localFont({ src: "../fonts/familjen-caps.woff2", weight: "500", variable: "--font-caps" });

export const metadata: Metadata = {
  title: SITE_NAME,
  description:
    "Each Betr pick'em prop's fair hit chance from sportsbook no-vig odds, against Betr's breakeven.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable} ${caps.variable}`}>
      <body>{children}</body>
    </html>
  );
}
