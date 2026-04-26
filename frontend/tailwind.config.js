/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        surface: "#0f1117",
        card:    "#1a1d27",
        border:  "#2a2d3e",
        accent:  "#3b82f6",
      },
    },
  },
  plugins: [],
}
