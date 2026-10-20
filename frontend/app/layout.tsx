import type { Metadata, Viewport } from "next";
import SiteHeader from "@/components/SiteHeader";
import "@fontsource/spectral/400.css";
import "@fontsource/spectral/400-italic.css";
import "@fontsource/spectral/500.css";
import "@fontsource/spectral/600.css";
import "@fontsource/spectral/700.css";
import "@fontsource/noto-nastaliq-urdu/arabic-400.css";
import "@fontsource/noto-nastaliq-urdu/arabic-600.css";
import "./globals.css";


export const metadata: Metadata = {
  title: "Dafa: Pakistan's law, section by section",
  description:
    "Ask about Pakistan's Constitution and Penal Code in English, Urdu or Roman Urdu. Every answer cites the exact section, checked against the official text.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#e9efe8" },
    { media: "(prefers-color-scheme: dark)", color: "#12221c" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SiteHeader />
        {children}
      </body>
    </html>
  );
}
