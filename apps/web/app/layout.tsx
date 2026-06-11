import type { ReactNode } from "react";
import { Fraunces, Inter } from "next/font/google";

import "./globals.css";
import { ThemeProvider } from "./theme";

const fraunces = Fraunces({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-display",
});
const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-sans",
});

export const metadata = {
  title: "Mise",
  description: "AI meal planning — plan, shop, cook, repeat.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  // `data-theme` is set on the client by ThemeProvider; default to warm for SSR.
  return (
    <html lang="en" data-theme="warm" className={`${fraunces.variable} ${inter.variable}`}>
      <body>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
