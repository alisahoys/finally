import type { Metadata } from "next";
import { Sofia_Sans_Semi_Condensed } from "next/font/google";
import type { ReactNode } from "react";
import "./globals.css";

const sofia = Sofia_Sans_Semi_Condensed({ subsets: ["latin"], variable: "--font-sofia" });

export const metadata: Metadata = {
  title: "FinAlly",
  description: "AI trading workstation with live prices and a simulated portfolio.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={sofia.variable}>
      <body>{children}</body>
    </html>
  );
}
