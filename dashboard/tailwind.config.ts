import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        obsidian: "#0B0E11",
        panel: "#151921",
        card: "#1E2329",
        well: "#262C36",
        hairline: "#2B3139",
        cyan: {
          DEFAULT: "#00E5FF",
          400: "#22d3ee",
          500: "#00E5FF",
          600: "#0891b2",
        },
        mint: {
          DEFAULT: "#0ECB81",
          400: "#34d399",
          500: "#0ECB81",
          600: "#059669",
        },
        coral: {
          DEFAULT: "#F6465D",
          400: "#fb7185",
          500: "#F6465D",
          600: "#e11d48",
        },
        gold: {
          DEFAULT: "#F0B90B",
          400: "#fbbf24",
          500: "#F0B90B",
          600: "#d97706",
        },
        violet: {
          DEFAULT: "#8B5CF6",
          500: "#8B5CF6",
          600: "#7c3aed",
        },
        surface: {
          50: "#f8fafc",
          100: "#f1f5f9",
          800: "#1e293b",
          900: "#0f172a",
          950: "#020617",
        },
        brand: {
          primary: "#00E5FF",
          accent: "#8B5CF6",
          cyan: "#00E5FF",
          emerald: "#0ECB81",
        }
      },
    },
  },
  plugins: [],
};
export default config;
