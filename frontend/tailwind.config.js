/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Cinemate palette — deep cinematic dark with amber accent
        brand: {
          bg: "#0A0A0F",
          surface: "#12121A",
          card: "#1A1A26",
          border: "#2A2A3A",
          amber: "#F5A623",
          "amber-dim": "#C4841C",
          text: "#E8E8F0",
          muted: "#8888A8",
        },
      },
      fontFamily: {
        display: ["'Playfair Display'", "serif"],
        body: ["'Inter'", "sans-serif"],
      },
    },
  },
  plugins: [],
}
