import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { MobileNav } from "@/components/MobileNav";
import { SmartDashboardPanel } from "@/components/SmartDashboardPanel";
import { WorkspaceProvider } from "@/components/WorkspaceContext";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "OnQue Workspace",
  description: "Gemini 기반 업무 자동화 워크스페이스",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <WorkspaceProvider>
          <div className="flex min-h-screen">
            <Sidebar />
            <div className="flex min-h-screen min-w-0 flex-1 flex-col">
              <MobileNav />
              <main className="flex-1 overflow-y-auto">{children}</main>
            </div>
            <SmartDashboardPanel />
          </div>
        </WorkspaceProvider>
      </body>
    </html>
  );
}
