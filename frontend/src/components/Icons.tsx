/** Küçük, tek renkli çizgi ikonlar (ek paket gerekmesin diye elle çizildi). */
const base = {
  width: 22,
  height: 22,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
};

export const DropIcon = () => (
  <svg {...base}>
    <path d="M12 3s-6 7-6 11a6 6 0 0 0 12 0c0-4-6-11-6-11z" />
  </svg>
);

export const CalendarIcon = () => (
  <svg {...base}>
    <rect x="3" y="5" width="18" height="16" rx="3" />
    <path d="M3 10h18M8 3v4M16 3v4" />
  </svg>
);

export const PeakIcon = () => (
  <svg {...base}>
    <path d="M3 17l5-6 4 3 5-8 4 5" />
    <path d="M3 21h18" />
  </svg>
);

export const MoonIcon = () => (
  <svg {...base}>
    <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
  </svg>
);

export const AlertIcon = () => (
  <svg {...base}>
    <path d="M12 3l9.5 16.5H2.5L12 3z" />
    <path d="M12 10v4M12 17.5v.01" />
  </svg>
);

export const WaveIcon = () => (
  <svg {...base}>
    <path d="M2 8c2.5-2 4.5-2 7 0s4.5 2 7 0 4.5-2 6 0" />
    <path d="M2 14c2.5-2 4.5-2 7 0s4.5 2 7 0 4.5-2 6 0" />
  </svg>
);

export const ChartIcon = () => (
  <svg {...base}>
    <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
  </svg>
);

export const ShieldIcon = () => (
  <svg {...base}>
    <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z" />
    <path d="M9 12l2 2 4-4" />
  </svg>
);

export const CloseIcon = () => (
  <svg {...base}>
    <path d="M6 6l12 12M18 6L6 18" />
  </svg>
);

export const RefreshIcon = () => (
  <svg {...base}>
    <path d="M20 11a8 8 0 1 0-2.3 5.7" />
    <path d="M20 4v7h-7" />
  </svg>
);
