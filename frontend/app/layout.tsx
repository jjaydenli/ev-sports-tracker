import type { Metadata } from "next";

import { SITE_NAME } from "@/lib/board";

import "./globals.css";

export const metadata: Metadata = {
  title: SITE_NAME,
  description:
    "Each Betr pick'em prop's fair hit chance from sportsbook no-vig odds, against Betr's breakeven.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
