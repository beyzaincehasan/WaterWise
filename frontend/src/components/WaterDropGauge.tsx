import { useEffect, useState } from 'react';
import { useCountUp } from '../hooks/useCountUp';
import { formatNumber } from '../utils/format';

interface Props {
  /** 0 – 1 arası doluluk */
  ratio: number;
  value: number;
  unit: string;
  caption: string;
  tone?: 'ok' | 'warn' | 'alert';
}

const DROP =
  'M100 8 C100 8 24 102 24 150 a76 76 0 0 0 152 0 C176 102 100 8 100 8 Z';
// Yatayda 80 birim periyotla tekrar eden dalga, kaydırınca kesintisiz döner.
const WAVE = 'M-160 0 Q-140 -10 -120 0 T-80 0 T-40 0 T0 0 T40 0 T80 0 T120 0 T160 0 T200 0 T240 0 T280 0 T320 0 V260 H-160 Z';

/** İçindeki su seviyesi animasyonla yükselen damla göstergesi. */
export function WaterDropGauge({ ratio, value, unit, caption, tone = 'ok' }: Props) {
  const [level, setLevel] = useState(0);
  const shown = useCountUp(value);

  useEffect(() => {
    const id = requestAnimationFrame(() => setLevel(Math.max(0, Math.min(1, ratio))));
    return () => cancelAnimationFrame(id);
  }, [ratio]);

  // Damlanın su alabilen kısmı y=20..226 arası.
  const surfaceY = 226 - level * 206;

  return (
    <div className={`gauge gauge--${tone}`}>
      <svg viewBox="0 0 200 240" className="gauge__svg" role="img" aria-label={caption}>
        <defs>
          <clipPath id="gauge-clip">
            <path d={DROP} />
          </clipPath>
          <linearGradient id="gauge-water" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" className="gauge__stop-top" />
            <stop offset="100%" className="gauge__stop-bottom" />
          </linearGradient>
        </defs>

        <path d={DROP} className="gauge__shell" />
        <g clipPath="url(#gauge-clip)">
          <g className="gauge__level" style={{ transform: `translateY(${surfaceY}px)` }}>
            <path d={WAVE} className="gauge__wave gauge__wave--back" />
            <path d={WAVE} className="gauge__wave gauge__wave--front" fill="url(#gauge-water)" />
          </g>
          <circle className="gauge__bubble" cx="80" cy="210" r="4" />
          <circle className="gauge__bubble gauge__bubble--2" cx="118" cy="214" r="3" />
          <circle className="gauge__bubble gauge__bubble--3" cx="100" cy="220" r="2.5" />
        </g>
        <path d={DROP} className="gauge__outline" />
        <ellipse cx="66" cy="128" rx="7" ry="20" className="gauge__glare" />
      </svg>

      <div className="gauge__readout">
        <span className="gauge__value">
          {formatNumber(shown, 1)}
          <small>{unit}</small>
        </span>
        <span className="gauge__caption">{caption}</span>
      </div>
    </div>
  );
}
