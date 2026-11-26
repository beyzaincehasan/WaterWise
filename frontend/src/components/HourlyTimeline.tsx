import { useEffect, useState, type CSSProperties } from 'react';
import type { AnomalyPredictionResponse } from '../api/types';
import { formatLiters, formatLocalTime, STATUS_META } from '../utils/format';
import { StatusBadge } from './StatusBadge';

interface Props {
  data: AnomalyPredictionResponse[] | undefined;
  loading: boolean;
}

/** Günün 24 saatini model sonucuna göre renklenen, yükselerek beliren sütunlarla gösterir. */
export function HourlyTimeline({ data, loading }: Props) {
  const [selected, setSelected] = useState<number | null>(null);

  // Yeni veri geldiğinde en dikkat çekici saati otomatik seç
  useEffect(() => {
    if (!data || data.length === 0) {
      setSelected(null);
      return;
    }
    const alertIdx = data.findIndex((d) => d.status === 'Anormal');
    const warnIdx = data.findIndex((d) => d.status === 'Şüpheli');
    const peakIdx = data.reduce(
      (best, d, i) => (d.consumption_liters > data[best].consumption_liters ? i : best),
      0,
    );
    setSelected(alertIdx >= 0 ? alertIdx : warnIdx >= 0 ? warnIdx : peakIdx);
  }, [data]);

  if (loading && !data) {
    return (
      <div className="timeline">
        <div className="timeline__bars">
          {Array.from({ length: 24 }, (_, i) => (
            <span key={i} className="timeline__bar skeleton" style={{ height: `${20 + ((i * 37) % 60)}%` }} />
          ))}
        </div>
        <p className="muted center">Model 24 saati tek tek değerlendiriyor…</p>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return <div className="empty">Bu gün için saatlik değerlendirme yok.</div>;
  }

  const max = Math.max(1, ...data.map((d) => d.consumption_liters), ...data.map((d) => d.normal_upper_liters ?? 0));
  const current = selected !== null ? data[selected] : null;

  return (
    <div className="timeline">
      <div className="timeline__bars" role="list">
        {data.map((d, i) => {
          const meta = STATUS_META[d.status];
          const upper = d.normal_upper_liters;
          return (
            <button
              key={d.timestamp}
              role="listitem"
              type="button"
              className={`timeline__slot ${selected === i ? 'is-selected' : ''} ${d.is_night ? 'is-night' : ''}`}
              onClick={() => setSelected(i)}
              title={`${formatLocalTime(d.timestamp_local)} · ${formatLiters(d.consumption_liters)} · ${meta.label}`}
            >
              {upper !== null && (
                <span className="timeline__upper" style={{ bottom: `${(upper / max) * 100}%` }} />
              )}
              <span
                className={`timeline__bar timeline__bar--${meta.tone}`}
                style={
                  {
                    height: `${Math.max(3, (d.consumption_liters / max) * 100)}%`,
                    '--i': i,
                  } as CSSProperties
                }
              />
            </button>
          );
        })}
      </div>
      <div className="timeline__axis">
        {['00', '06', '12', '18', '23'].map((h) => (
          <span key={h}>{h}:00</span>
        ))}
      </div>

      {current && (
        <div className={`timeline__detail tone-${STATUS_META[current.status].tone}`} key={current.timestamp}>
          <div className="timeline__detail-head">
            <div>
              <span className="muted">Saat {formatLocalTime(current.timestamp_local)}{current.is_night ? ' · gece' : ''}</span>
              <strong>{formatLiters(current.consumption_liters)}</strong>
            </div>
            <StatusBadge status={current.status} />
          </div>
          <p>{current.message}</p>
          {current.reasons.length > 0 && (
            <ul className="reasons">
              {current.reasons.map((r) => (
                <li key={r.code}>{r.text}</li>
              ))}
            </ul>
          )}
          <dl className="facts">
            <div>
              <dt>Bu saat normalde</dt>
              <dd>{formatLiters(current.normal_consumption_liters)}</dd>
            </div>
            <div>
              <dt>Normal üst sınır</dt>
              <dd>{formatLiters(current.normal_upper_liters)}</dd>
            </div>
            <div>
              <dt>Sürekli akış</dt>
              <dd>{current.continuous_activity_minutes} dk</dd>
            </div>
            <div>
              <dt>Model skoru</dt>
              <dd title="Göreli aykırılık göstergesidir, yüzde veya olasılık değildir.">
                {current.anomaly_score.toFixed(3)}
                <small> / eşik {current.thresholds.anomalous.toFixed(3)}</small>
              </dd>
            </div>
          </dl>
        </div>
      )}
    </div>
  );
}
