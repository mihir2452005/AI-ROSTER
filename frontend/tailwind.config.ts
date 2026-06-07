import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  // Use class strategy so we can flip themes via document.documentElement.classList.
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Default (dark) palette — the base.
        bg:        "rgb(var(--c-bg) / <alpha-value>)",
        surface:   "rgb(var(--c-surface) / <alpha-value>)",
        border:    "rgb(var(--c-border) / <alpha-value>)",
        accent:    "rgb(var(--c-accent) / <alpha-value>)",
        "accent-2": "rgb(var(--c-accent-2) / <alpha-value>)",
        "accent-3": "rgb(var(--c-accent-3) / <alpha-value>)",
        success:   "rgb(var(--c-success) / <alpha-value>)",
        muted:     "rgb(var(--c-muted) / <alpha-value>)",
        text:      "rgb(var(--c-text) / <alpha-value>)",
      },
      fontFamily: {
        // "RoastGPT-Emoji" is the unicode-range @font-face defined
        // in app/globals.css. It only "owns" emoji code points, so
        // for ASCII text the browser falls through to the next entry
        // (the Inter variable) without an extra HTTP request.
        sans:    ["RoastGPT-Emoji", "var(--font-inter)", "Inter", "system-ui", "sans-serif"],
        mono:    ["var(--font-jetbrains-mono)", "JetBrains Mono", "ui-monospace", "monospace"],
        display: ["RoastGPT-Emoji", "var(--font-inter)", "Inter", "sans-serif"],
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
