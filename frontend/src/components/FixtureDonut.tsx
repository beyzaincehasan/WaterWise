import { useEffect, useState, type CSSProperties } from 'react';
import type { FixtureBreakdownItem } from '../api/types';
import { formatLiters, formatNumber } from '../utils/format';

const COLORS: Record<string, string> = {
  Duş: '#38bdf8',
  Musluk: '#2dd4bf',
  Tuvalet: '#818cf8',
  Makine: '#c084fc',
  Diğer: '#94a3b8',
};
const FALLBACK = ['#60a5fa', '#34d399', '#f472b6', '#fbbf24'];

const ICONS: Record<string, string> = {
  Duş: '🚿',
  Musluk: '🚰',
  Tuvalet: '🚽',
  Makine: '🧺',
  Diğer: '💧',
};

const R = 80;
const C = 2 * Math.PI * R;

/** Kullanım dağılımı halkası; dilimler sırayla dolarak açılır. */
export function FixtureDonut({ data }: { data: FixtureBreakdownItem[] }) {
  const [grown, setGrown] = useState(false);
  const [active, setActive] = useState<number | null>(null);

  useEffect(() => {
    setGrown(false);
    const id = window.setTimeout(() => setGrown(true), 60);
    return () => window.clearTimeout(id);
  }, [data]);

  if (data.length === 0) {
    return <div className="empty">Kullanım dağılımı verisi yok.</div>;
  }

  const total = data.reduce((sum, d) => sum + d.total_liters, 0);
  const color = (name: string, i: number) => COLORS[name] ?? FALLBACK[i % FALLBACK.length];

  let offset = 0;
  const segments = data.map((d, i) => {
    const length = total > 0 ? (d.total_liters / total) * C : 0;
    const seg = { ...d, length, offset, color: color(d.fixture, i) };
    offset += length;
    return seg;
  });

  const focus = active !== null ? segments[active] : null;

  return (
    <div className="donut">
      <svg viewBox="0 0 220 220" className="donut__svg">
        <circle cx="110" cy="110" r={R} className="donut__track" />
        <g transform="rotate(-90 110 110)">
          {segments.map((s, i) => (
            <circle
              key={s.fixture}
              cx="110"
              cy="110"
              r={R}
              className={`donut__seg ${active === i ? 'is-active' : ''}`}
              stroke={s.color}
              strokeDasharray={`${grown ? Math.max(0, s.length - 3) : 0} ${C}`}
              strokeDashoffset={-s.offset}
              style={{ transitionDelay: `${i * 120}ms` } as CSSProperties}
              onMouseEnter={() => setActive(i)}
              onMouseLeave={() => setActive(null)}
            />
          ))}
        </g>
        <text x="110" y="104" textAnchor="middle" className="donut__center-label">
          {focus ? focus.fixture : 'Toplam'}
        </text>
        <text x="110" y="128" textAnchor="middle" className="donut__center-value">
          {focus ? `%${formatNumber(focus.percentage, 1)}` : formatLiters(total, 0)}
        </text>
      </svg>

      <ul className="donut__legend">
        {segments.map((s, i) => (
          <li
            key={s.fixture}
            className={active === i ? 'is-active' : ''}
            onMouseEnter={() => setActive(i)}
            onMouseLeave={() => setActive(null)}
            style={{ '--c': s.color, '--i': i } as CSSProperties}
          >
            <span className="donut__emoji">{ICONS[s.fixture] ?? '💧'}</span>
            <div className="donut__row">
              <div className="donut__row-top">
                <span>{s.fixture}</span>
                <span>
                  {formatLiters(s.total_liters, 0)} · %{formatNumber(s.percentage, 1)}
                </span>
              </div>
              <div className="donut__bar">
                <span style={{ width: grown ? `${s.percentage}%` : 0 }} />
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
