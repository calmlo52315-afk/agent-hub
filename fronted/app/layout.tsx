import type { Metadata } from "next";
import { TopNavBar } from "@/components/layout/TopNavBar";
import "./globals.css";

export const metadata: Metadata = {
  title: "AgentHub — Multi-Agent Collaboration Platform",
  description:
    "AI-powered multi-agent coding collaboration platform with real-time IM chat, task tracking, code review, and artifact management.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="zh-CN"
      className="h-full antialiased"
      suppressHydrationWarning
    >
      <body className="h-full bg-[#E5E5E5] overflow-hidden">
        {/* Full screen layout with padding */}
        <div className="h-full p-3 box-border">
          <main className="h-full w-full">{children}</main>
        </div>
      </body>
    </html>
  );
}
