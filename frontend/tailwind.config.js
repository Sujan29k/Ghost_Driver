/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ghost: {
          bg: '#050a0f',
          surface: '#0d1821',
          panel: '#0f1f2e',
          border: '#1a3a5c',
          accent: '#00d4ff',
          accentDim: '#0090b0',
          success: '#00ff87',
          warning: '#ffaa00',
          danger: '#ff3b5c',
          text: '#c8dff0',
          muted: '#5a7a95',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'scan': 'scan 4s linear infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
        'spin-slow': 'spin 8s linear infinite',
      },
      keyframes: {
        scan: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100vh)' },
        },
        glow: {
          '0%': { boxShadow: '0 0 5px #00d4ff40' },
          '100%': { boxShadow: '0 0 20px #00d4ff, 0 0 40px #00d4ff40' },
        },
      },
      backdropBlur: {
        xs: '2px',
      },
    },
  },
  plugins: [],
};
