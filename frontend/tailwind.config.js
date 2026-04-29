/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Hotpot palette — keep in sync with the deck.
        brand: {
          DEFAULT: "#C4302B",
          dark: "#1A1F3A",
          amber: "#F4A261",
          tint: "#FBE7E5",
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
