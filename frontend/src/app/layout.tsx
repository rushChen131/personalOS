import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { AppShell } from "@/components/AppShell";

export const metadata: Metadata = {
  title: "PersonalOS",
  description: "Personal life operating system — journals, goals, events, memories and AI insight.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // Chinese is the default locale; the LanguageToggle keeps this attribute in sync.
  return (
    <html lang="zh-CN">
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
