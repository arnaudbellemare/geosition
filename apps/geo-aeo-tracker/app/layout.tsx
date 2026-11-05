import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GEO/AEO Tracker",
  description: "BYOK AEO/GEO intelligence dashboard with local-first persistence",
};

/** Inline script to apply theme before first paint — prevents flash */
const themeScript = `(function(){try{var t=localStorage.getItem('sovereign-theme');if(t==='dark'||(t!=='light'&&window.matchMedia('(prefers-color-scheme:dark)').matches)){document.documentElement.classList.add('dark')}}catch(e){}})()`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body suppressHydrationWarning className="antialiased">
        {children}
      </body>
    </html>
  );
}
