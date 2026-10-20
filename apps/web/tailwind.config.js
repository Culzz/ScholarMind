/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      colors: {
        // Claim-state palette. Single source of truth lives in src/lib/claims.ts —
        // these tokens exist so Tailwind can generate the utility classes used there.
        claim: {
          confirmed: {
            DEFAULT: '#047857',
            soft: '#ecfdf5',
            border: '#a7f3d0',
            text: '#065f46',
          },
          notEstablished: {
            DEFAULT: '#b45309',
            soft: '#fffbeb',
            border: '#fde68a',
            text: '#92400e',
          },
          needsVerification: {
            DEFAULT: '#be123c',
            soft: '#fff1f2',
            border: '#fecdd3',
            text: '#9f1239',
          },
          stale: {
            DEFAULT: '#475569',
            soft: '#f1f5f9',
            border: '#cbd5e1',
            text: '#334155',
          },
          expired: {
            DEFAULT: '#52525b',
            soft: '#fafafa',
            border: '#e4e4e7',
            text: '#3f3f46',
          },
        },
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(2px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 150ms ease-out',
      },
    },
  },
  plugins: [],
};
