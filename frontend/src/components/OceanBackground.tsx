import { useMemo, type CSSProperties } from 'react';

/** Sayfanın arkasındaki derin su: ışık huzmeleri, yükselen kabarcıklar ve dalgalar. */
const WAVE_PATH =
  'M0,50 Q180,10 360,50 T720,50 T1080,50 T1440,50 T1800,50 T2160,50 T2520,50 T2880,50 V120 H0 Z';

export function OceanBackground() {
  const bubbles = useMemo(
    () =>
      Array.from({ length: 22 }, (_, i) => ({
        id: i,
        left: Math.random() * 100,
        size: 4 + Math.random() * 14,
        duration: 9 + Math.random() * 14,
        delay: -Math.random() * 20,
        drift: (Math.random() - 0.5) * 60,
      })),
    [],
  );

  return (
    <div className="ocean" aria-hidden="true">
      <div className="ocean__rays">
        <span />
        <span />
        <span />
      </div>

      {bubbles.map((b) => (
        <span
          key={b.id}
          className="bubble"
          style={
            {
              left: `${b.left}%`,
              width: b.size,
              height: b.size,
              animationDuration: `${b.duration}s`,
              animationDelay: `${b.delay}s`,
              '--drift': `${b.drift}px`,
            } as CSSProperties
          }
        />
      ))}

      <div className="ocean__waves">
        {[0, 1, 2].map((layer) => (
          <svg
            key={layer}
            className={`wave wave--${layer}`}
            viewBox="0 0 2880 120"
            preserveAspectRatio="none"
          >
            <path d={WAVE_PATH} />
          </svg>
        ))}
      </div>
    </div>
  );
}
