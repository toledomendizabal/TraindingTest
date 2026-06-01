/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#e6fff9',
          100: '#b3ffe8',
          200: '#80ffd7',
          300: '#4dffc6',
          400: '#1affb5',
          500: '#00d4aa',
          600: '#00a888',
          700: '#007d66',
          800: '#005244',
          900: '#002722',
        },
        dark: {
          100: '#1e293b',
          200: '#1a1a2e',
          300: '#16213e',
          400: '#0f172a',
          500: '#0a0e1a',
        }
      }
    },
  },
  plugins: [],
}
