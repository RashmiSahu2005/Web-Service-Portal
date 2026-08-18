/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#f8f9fa',
        surface: '#ffffff',
        primary: '#004aad', // Dark blue from the screenshot
        secondary: '#6b7280', // Gray-500
        accent: '#3b82f6',
      }
    },
  },
  plugins: [],
}
