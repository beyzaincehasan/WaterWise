import { useState, type CSSProperties } from 'react';
import { api } from '../api/client';
import { useAsync } from '../hooks/useAsync';
import { formatLiters, formatLocalDateTime, STATUS_META } from '../utils/format';
import { StatusBadge } from './StatusBadge';
import { RefreshIcon } from './Icons';

type Filter = 'all' | 'Anormal' | 'Şüpheli';

interface Props {
  apartmentId: string;
  /** Dışarıdan artırıldığında liste yenilenir (ör. simülasyondan sonra) */
  refreshKey: number;
}

/** Kayıtlı anomali olaylarının kayarak gelen kart akışı. */
export function AnomalyFeed({ apartmentId, refreshKey }: Props) {
  const [filter, setFilter] = useState<Filter>('all');
  const [onlyThis, setOnlyThis] = useState(true);

  const { data, loading, error, reload } = useAsync(
    () =>
      api.anomalies({
        apartmentId: onlyThis ? apartmentId : undefined,
        status: filter === 'all' ? undefined : filter,
        limit: 60,
      }),
    [apartmentId, filter, onlyThis, refreshKey],
  );

  return (
    <section className="card feed">
      <header className="card__head">
        <div>
          <h3>Uyarı geçmişi</h3>
          <p className="muted">Modelin kaydettiği şüpheli ve anormal saatler</p>
        </div>
        <button type="button" className={`icon-btn ${loading ? 'is-spinning' : ''}`} onClick={reload} aria-label="Yenile">
          <RefreshIcon />
        </button>
      </header>

      <div className="feed__filters">
        {(['all', 'Anormal', 'Şüpheli'] as Filter[]).map((f) => (
          <button
            key={f}
            type="button"
            className={`pill ${filter === f ? 'is-active' : ''}`}
            onClick={() => setFilter(f)}
          >
            {f === 'all' ? 'Tümü' : f}
          </button>
        ))}
        <label className="toggle">
          <input type="checkbox" checked={onlyThis} onChange={(e) => setOnlyThis(e.target.checked)} />
          <span className="toggle__track" />
          Sadece {apartmentId.replace('APT_', 'Daire ')}
        </label>
      </div>

      {error && <div className="error">{error}</div>}

      {!error && data && data.length === 0 && (
        <div className="empty empty--calm">
          <span className="empty__ripple" />
          Kayıtlı uyarı yok. Sular durgun. 🌊
        </div>
      )}

      <ul className="feed__list">
        {data?.map((item, i) => (
          <li
            key={item.id}
            className={`feed__item tone-${STATUS_META[item.status].tone}`}
            style={{ '--i': Math.min(i, 12) } as CSSProperties}
          >
            <div className="feed__item-head">
              <StatusBadge status={item.status} />
              <span className="muted">{formatLocalDateTime(item.timestamp_local)}</span>
              <span className="feed__apt">{item.apartment_id.replace('APT_', 'Daire ')}</span>
              {item.is_demo && <span className="chip chip--demo">demo</span>}
              <strong className="feed__liters">{formatLiters(item.consumption_liters)}</strong>
            </div>
            <p>{item.message}</p>
            {item.reasons.length > 0 && (
              <ul className="reasons">
                {item.reasons.map((r) => (
                  <li key={r.code}>{r.text}</li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
