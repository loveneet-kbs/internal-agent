/** @type {import('tailwindcss').Config} */

// Every colour resolves to a CSS variable defined in src/index.css, so the same
// class works in both themes and no component hardcodes a palette shade.
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        backdrop: token("backdrop"),
        "backdrop-2": token("backdrop-2"),
        glass: token("glass"),
        line: token("border"),

        text: token("text"),
        "text-2": token("text-2"),
        muted: token("muted"),

        accent: token("accent"),
        "accent-soft": token("accent-soft"),
        success: token("success"),
        danger: token("danger"),
        warning: token("warning"),
        info: token("info")
      },
      fontFamily: {
        sans: ["DM Sans", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"]
      },
      animation: {
        "pulse-soft": "pulse-soft 1.6s ease-in-out infinite",
        "slide-in": "slide-in 0.28s cubic-bezier(0.34, 1.3, 0.64, 1)",
        "fade-in": "fade-in 0.2s ease-out",
        shimmer: "shimmer 1.8s linear infinite"
      },
      keyframes: {
        "pulse-soft": {
          "0%, 100%": { opacity: 1 },
          "50%": { opacity: 0.45 }
        },
        "slide-in": {
          from: { opacity: 0, transform: "translateY(8px)" },
          to: { opacity: 1, transform: "translateY(0)" }
        },
        "fade-in": {
          from: { opacity: 0 },
          to: { opacity: 1 }
        },
        shimmer: {
          from: { backgroundPosition: "-200% 0" },
          to: { backgroundPosition: "200% 0" }
        }
      }
    }
  },
  plugins: []
};
