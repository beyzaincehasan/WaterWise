import { useMemo, useState } from 'react';
import type { DailyConsumptionItem } from '../api/types';
import { formatLiters, formatLongDate, formatShortDate, formatNumber } from '../utils/format';

interface Props {
  data: DailyConsumptionItem[];
  /** Normal günlük aralık [p05, p95]; varsa grafikte bant olarak çizilir */
  normalRange?: [number, number] | null;
  height?: number;
}

const W = 860;
const PAD = { top: 20, right: 18, bottom: 34, left: 52 };

function niceMax(value: number): number {
  if (value <= 0) return 10;
  const exp = Math.pow(10, Math.floor(Math.log10(value)));
  const steps = [1, 2, 2.5, 5, 10];
  const n = value / exp;
  const step = steps.find((s) => s >= n) ?? 10;
  return step * exp;
}

/** Toplam, soğuk ve sıcak su tüketimini çizilerek beliren eğrilerle gösterir. */
export function DailyChart({ data, normalRange, height = 280 }: Props) {
  const [hover, setHover] = useState<number | null>(null);

  const geometry = useMemo(() => {
    const innerW = W - PAD.left - PAD.right;
    const innerH = height - PAD.top - PAD.bottom;
    const peak = Math.max(
      1,
      ...data.map((d) => d.total_liters),
      normalRange ? normalRange[1] : 0,
    );
    const maxY = niceMax(peak * 1.08);
    const x = (i: number) =>
      PAD.left + (data.length <= 1 ? innerW / 2 : (i / (data.length - 1)) * innerW);
    const y = (v: number) => PAD.top + innerH - (v / maxY) * innerH;

    const line = (key: 'total_liters' | 'cold_water_liters' | 'hot_water_liters') => {
      if (data.length === 0) return '';
      // Yumuşak eğri için noktalar arası kübik bezier
      return data
        .map((d, i) => {
          const px = x(i);
          const py = y(d[key]);
          if (i === 0) return `M${px},${py}`;
          const prevX = x(i - 1);
          const prevY = y(data[i - 1][key]);
          const cx = (prevX + px) / 2;
          return `C${cx},${prevY} ${cx},${py} ${px},${py}`;
        })
        .join(' ');
    };

    const total = line('total_liters');
    const area = data.length
      ? `${total} L${x(data.length - 1)},${y(0)} L${x(0)},${y(0)} Z`
      : '';
    const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * maxY);
    const labelEvery = Math.max(1, Math.ceil(data.length / 8));

    return {
      innerW,
      x,
      y,
      total,
      area,
      cold: line('cold_water_liters'),
      hot: line('hot_water_liters'),
      ticks,
      labelEvery,
      slot: data.length > 1 ? innerW / (data.length - 1) : innerW,
    };
  }, [data, normalRange, height]);

  if (data.length === 0) {
    return <div className="empty">Bu dönem için tüketim kaydı bulunamadı.</div>;
  }

  const hovered = hover !== null ? data[hover] : null;
  // Veri değişince animasyon baştan oynasın diye anahtar
  const animKey = `${data[0].date}-${data.length}`;

  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${height}`} className="chart__svg" key={animKey}>
        <defs>
          <linearGradient id="area-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#38bdf8" stopOpacity="0" />
          </linearGradient>
        </defs>

        {geometry.ticks.map((t) => (
          <g key={t}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={geometry.y(t)}
              y2={geometry.y(t)}
              className="chart__grid"
            />
            <text x={PAD.left - 10} y={geometry.y(t) + 4} className="chart__tick" textAnchor="end">
              {formatNumber(t, 0)}
            </text>
          </g>
        ))}

        {normalRange && (
          <rect
            x={PAD.left}
            width={geometry.innerW}
            y={geometry.y(normalRange[1])}
            height={Math.max(0, geometry.y(normalRange[0]) - geometry.y(normalRange[1]))}
            className="chart__band"
          />
        )}

        <path d={geometry.area} fill="url(#area-fill)" className="chart__area" />
        <path d={geometry.cold} className="chart__line chart__line--cold" pathLength={1} />
        <path d={geometry.hot} className="chart__line chart__line--hot" pathLength={1} />
        <path d={geometry.total} className="chart__line chart__line--total" pathLength={1} />

        {data.map((d, i) =>
          i % geometry.labelEvery === 0 || i === data.length - 1 ? (
            <text
              key={d.date}
              x={geometry.x(i)}
              y={height - 10}
              className="chart__tick"
              textAnchor="middle"
            >
              {formatShortDate(d.date)}
            </text>
          ) : null,
        )}

        {hovered && hover !== null && (
          <g className="chart__cursor">
            <line
              x1={geometry.x(hover)}
              x2={geometry.x(hover)}
              y1={PAD.top}
              y2={height - PAD.bottom}
            />
            <circle cx={geometry.x(hover)} cy={geometry.y(hovered.total_liters)} r="6" />
          </g>
        )}

        {data.map((d, i) => (
          <rect
            key={d.date}
            x={geometry.x(i) - geometry.slot / 2}
            y={PAD.top}
            width={geometry.slot}
            height={height - PAD.top - PAD.bottom}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
          />
        ))}
      </svg>

      {hovered && hover !== null && (
        <div
          className="chart__tooltip"
          style={{
            left: `${(geometry.x(hover) / W) * 100}%`,
            top: `${(geometry.y(hovered.total_liters) / height) * 100}%`,
          }}
        >
          <strong>{formatLongDate(hovered.date)}</strong>
          <span>Toplam: {formatLiters(hovered.total_liters)}</span>
          <span className="t-cold">Soğuk: {formatLiters(hovered.cold_water_liters)}</span>
          <span className="t-hot">Sıcak: {formatLiters(hovered.hot_water_liters)}</span>
        </div>
      )}

      <div className="chart__legend">
        <span className="legend legend--total">Toplam</span>
        <span className="legend legend--cold">Soğuk su</span>
        <span className="legend legend--hot">Sıcak su</span>
        {normalRange && <span className="legend legend--band">Normal günlük aralık</span>}
      </div>
    </div>
  );
}
