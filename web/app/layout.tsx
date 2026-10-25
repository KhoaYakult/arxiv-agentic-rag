import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono, Source_Serif_4 } from "next/font/google";
import "katex/dist/katex.min.css";
import "./globals.css";
import { BRAND } from "@/lib/brand";

const geist = Geist({ subsets: ["latin", "vietnamese"], variable: "--font-geist" });
const geistMono = Geist_Mono({ subsets: ["latin", "vietnamese"], variable: "--font-geist-mono" });
const sourceSerif = Source_Serif_4({
  subsets: ["latin", "vietnamese"],
  variable: "--font-source-serif",
  axes: ["opsz"],
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: BRAND.name,
  description: BRAND.tagline,
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#faf8f4" },
    { media: "(prefers-color-scheme: dark)", color: "#161513" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" className={`${geist.variable} ${geistMono.variable} ${sourceSerif.variable}`}>
      <body>{children}</body>
    </html>
  );
}
