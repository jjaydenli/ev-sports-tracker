import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "EV board",
  description: "Betr pick'em props priced against DraftKings and FanDuel no-vig odds.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
