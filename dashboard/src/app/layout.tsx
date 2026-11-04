import type { Metadata, Viewport } from "next";
import "./globals.css";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  themeColor: "#0B0E11",
};

export const metadata: Metadata = {
  metadataBase: new URL("https://bitdex.ltd"),
  title: "BITDEX — Institutional Quantitative AI & Trading Terminal",
  description: "Non-custodial quantitative AI intelligence, chartless multi-market regime analysis, and risk-guarded execution terminal for Exness and Binance traders.",
  keywords: [
    "BITDEX",
    "quantitative trading terminal",
    "institutional AI market analysis",
    "Exness MT5 gateway",
    "Binance futures scalping",
    "non-custodial trading intelligence",
    "chartless trading terminal"
  ],
  alternates: {
    canonical: "https://bitdex.ltd",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
  openGraph: {
    title: "BITDEX — Institutional Quantitative AI & Trading Terminal",
    description: "Non-custodial quantitative AI intelligence, chartless multi-market regime analysis, and risk-guarded execution terminal for Exness and Binance traders.",
    url: "https://bitdex.ltd",
    siteName: "BITDEX",
    images: [
      {
        url: "https://bitdex.ltd/bitdex-logo.svg",
        width: 1200,
        height: 630,
        alt: "BITDEX Quantitative Intelligence",
      },
    ],
    locale: "en_US",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "BITDEX — Institutional Quantitative AI & Trading Terminal",
    description: "Non-custodial quantitative AI intelligence, chartless multi-market regime analysis, and risk-guarded execution terminal for Exness and Binance traders.",
    images: ["https://bitdex.ltd/bitdex-logo.svg"],
  },
  icons: {
    icon: [
      { url: "/bitdex-icon.svg", type: "image/svg+xml" },
      { url: "/favicon.ico" }
    ],
    shortcut: "/bitdex-icon.svg",
    apple: "/bitdex-icon.svg",
  },
};

const structuredData = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": "https://bitdex.ltd/#organization",
      "name": "BITDEX",
      "url": "https://bitdex.ltd",
      "logo": "https://bitdex.ltd/bitdex-logo.svg",
      "description": "Institutional Quantitative AI & Execution Platform for Modern Digital Asset and Multi-Asset Traders"
    },
    {
      "@type": "WebSite",
      "@id": "https://bitdex.ltd/#website",
      "url": "https://bitdex.ltd",
      "name": "BITDEX",
      "publisher": { "@id": "https://bitdex.ltd/#organization" }
    },
    {
      "@type": "SoftwareApplication",
      "@id": "https://bitdex.ltd/#application",
      "name": "BITDEX Institutional Terminal",
      "applicationCategory": "FinanceApplication",
      "operatingSystem": "Web",
      "url": "https://bitdex.ltd",
      "provider": { "@id": "https://bitdex.ltd/#organization" },
      "description": "Chartless institutional trading terminal featuring multi-agent AI regime analysis, pre-trade risk guardrails, and non-custodial execution."
    },
    {
      "@type": "FinancialService",
      "@id": "https://bitdex.ltd/#service",
      "name": "BITDEX Quantitative Intelligence",
      "url": "https://bitdex.ltd",
      "provider": { "@id": "https://bitdex.ltd/#organization" },
      "serviceType": "Quantitative Trading Analytics & Decision Support",
      "description": "Non-custodial algorithmic intelligence, multi-agent AI regime analysis, and trade confirmation tools."
    }
  ]
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
        />
      </head>
      <body className="bg-[#0B0E11] text-[#EAECEF] min-h-screen antialiased selection:bg-[#00E5FF] selection:text-[#0B0E11]">
        {children}
      </body>
    </html>
  );
}
