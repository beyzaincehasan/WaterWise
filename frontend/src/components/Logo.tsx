/** İçinde dalgalanan su olan damla logosu. */
export function Logo({ size = 40 }: { size?: number }) {
  return (
    <svg className="logo-drop" width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <defs>
        <clipPath id="logo-clip">
          <path d="M32 4 C32 4 10 30 10 42 a22 22 0 0 0 44 0 C54 30 32 4 32 4 Z" />
        </clipPath>
        <linearGradient id="logo-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#7dd3fc" />
          <stop offset="100%" stopColor="#0369a1" />
        </linearGradient>
      </defs>
      <path
        d="M32 4 C32 4 10 30 10 42 a22 22 0 0 0 44 0 C54 30 32 4 32 4 Z"
        fill="rgba(125, 211, 252, 0.15)"
        stroke="#7dd3fc"
        strokeWidth="2"
      />
      <g clipPath="url(#logo-clip)">
        <path
          className="logo-drop__wave"
          d="M-64 36 Q-48 30 -32 36 T0 36 T32 36 T64 36 T96 36 V70 H-64 Z"
          fill="url(#logo-fill)"
        />
      </g>
      <ellipse cx="24" cy="38" rx="3" ry="6" fill="rgba(255,255,255,0.55)" />
    </svg>
  );
}
