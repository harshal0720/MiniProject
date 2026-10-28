import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#07060D",
        surface: "#0D0B15",
        elevated: "#141020",
        violet: { DEFAULT: "#8B5CF6", soft: "#A78BFA", pale: "#C4B5FD" },
        signal: "#22D3EE",
        good: "#A3E635",
        warning: "#FBBF24",
        critical: "#FB7185",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      boxShadow: {
        glow: "0 0 40px rgba(139, 92, 246, 0.10)",
      },
    },
  },
  plugins: [],
} satisfies Config;