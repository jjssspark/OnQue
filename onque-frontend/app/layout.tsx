import type { Metadata } from "next";
import { IBM_Plex_Sans_KR, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { WorkspaceProvider } from "@/components/WorkspaceContext";
import { AuthProvider } from "@/components/AuthContext";
import { AuthGuard } from "@/components/AuthGuard";

// IBM Plex Sans KR은 가변 글꼴이 아니라 weight를 명시해야 한다.
// preload를 끄는 이유는 한글이 next/font의 subsets 목록에 없어서다 —
// subsets: ['latin']만 주면 한글 글리프가 빠져 fallback으로 떨어진다.
const plexSans = IBM_Plex_Sans_KR({
  weight: ["400", "500", "600", "700"],
  preload: false,
  variable: "--font-plex-sans",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  weight: ["400", "500", "600"],
  subsets: ["latin"],
  variable: "--font-plex-mono",
  display: "swap",
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
    <html lang="ko" className={`${plexSans.variable} ${plexMono.variable}`}>
      <body className="antialiased">
        <AuthProvider>
          <WorkspaceProvider>
            <AuthGuard>{children}</AuthGuard>
          </WorkspaceProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
