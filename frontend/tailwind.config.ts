import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg:        "#0a0a0a",
        surface:   "#171717",
        border:    "#262626",
        accent:    "#ef4444",
        "accent-2": "#f97316",
        "accent-3": "#fbbf24",
        success:   "#22c55e",
        muted:     "#737373",
        text:      "#fafafa",
      },
      fontFamily: {
        sans:  ["Inter", "system-ui", "sans-serif"],
        mono:  ["JetBrains Mono", "monospace"],
        display: ["'Bricolage Grotesque'", "Inter", "sans-serif"],
      },
      animation: {
        "fade-in":   "fadeIn 0.4s ease-out",
        "slide-up":  "slideUp 0.4s ease-out",
        "shake":     "shake 0.4s ease-in-out",
        "pulse-red": "pulseRed 1.5s ease-in-out infinite",
      },
      keyframes: {
        fadeIn:   { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        slideUp:  { "0%": { opacity: "0", transform: "translateY(20px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        shake:    { "0%, 100%": { transform: "translateX(0)" }, "25%": { transform: "translateX(-4px)" }, "75%": { transform: "translateX(4px)" } },
        pulseRed: { "0%, 100%": { boxShadow: "0 0 0 0 rgba(239, 68, 68, 0.5)" }, "50%": { boxShadow: "0 0 0 12px rgba(239, 68, 68, 0)" } },
      },
    },
  },
  plugins: [],
};

export default config;
