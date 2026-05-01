/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Hotpot Direction G palette.
        brand: {
          DEFAULT: "#C8442C",
          dark: "#1A1410",
          amber: "#B8860B",
          tint: "#FCE9E2",
        },
      },
      fontFamily: {
        serif: ["Georgia", "ui-serif", "serif"],
        sans: ["ui-sans-serif", "system-ui", "Inter", "Calibri", "sans-serif"],
      },
    },
  },
  plugins: [],
};
