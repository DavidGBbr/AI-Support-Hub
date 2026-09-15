import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "AI Support Hub",
  description: "Local diagnostics for the AI Support Hub development stack.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
