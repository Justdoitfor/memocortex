import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { TopNav } from "@/components/layout/top-nav";
import { ApiStatus } from "@/components/layout/api-status";
import { QueryProvider } from "@/components/providers";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "MemoCortex — Agent 长期记忆中间件",
  description:
    "5 类分层记忆 / 4 信号 Hybrid Recall / LLM-as-Arbitrator 冲突自动消解",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-50">
        <QueryProvider>
          <TopNav />
          <main className="flex-1 mx-auto w-full max-w-7xl px-4 py-6">{children}</main>
          <footer className="border-t border-zinc-200 dark:border-zinc-800">
            <div className="mx-auto flex max-w-7xl items-center justify-between gap-2 px-4 py-3 text-xs text-zinc-500 dark:text-zinc-400">
              <span>
                MemoCortex MVP · MIT License · 用于"大模型应用开发岗"求职 Demo
              </span>
              <ApiStatus />
            </div>
          </footer>
        </QueryProvider>
      </body>
    </html>
  );
}
