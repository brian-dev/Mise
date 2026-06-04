import type { ReactNode } from "react";

export const metadata = {
  title: "Mise",
  description: "AI meal planning — plan, shop, cook, repeat.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
