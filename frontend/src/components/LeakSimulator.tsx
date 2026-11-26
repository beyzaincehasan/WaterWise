import { useState, type CSSProperties } from 'react';
import { api } from '../api/client';
import type { DemoSimulateResponse } from '../api/types';
import { shouldTriggerNotification } from '../api/types';
import { formatLiters, formatLocalTime } from '../utils/format';
import { StatusBadge } from './StatusBadge';

interface Props {
  apartmentId: string;
  onDone: (result: DemoSimulateResponse) => void;
}

/**
 * Sunum için canlı kaçak senaryosu: boru damlatır, model saatleri değerlendirir,
 * sonuçlar sırayla belirir.
 */
export function LeakSimulator({ apartmentId, onDone }: Props) {
  const [hours, setHours] = useState(3);
  const [rate, setRate] = useState(18);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<DemoSimulateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      // Damlama animasyonu en az bir an görünsün
      const [res] = await Promise.all([
        api.simulateDemo({ apartment_id: apartmentId, hours, rate_l_per_hour: rate }),
        new Promise((resolve) => setTimeout(resolve, 1400)),
      ]);
      setResult(res);
      onDone(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  };

  const alarm = result?.results.some((r) => shouldTriggerNotification(r.status)) ?? false;

  return (
    <section className={`card sim ${running ? 'is-running' : ''} ${alarm ? 'is-alarm' : ''}`}>
      <header className="card__head">
        <div>
          <h3>Canlı kaçak simülasyonu</h3>
          <p className="muted">
            Gece saatlerine sürekli akış eklenir ve modelin Normal → Anormal geçişi canlı izlenir.
          </p>
        </div>
      </header>

      <div className="sim__stage" aria-hidden="true">
        <svg viewBox="0 0 320 120" className="sim__pipe">
          <path d="M0 40 H200 Q220 40 220 60 V78" className="sim__pipe-body" />
          <path d="M0 40 H200 Q220 40 220 60 V78" className="sim__pipe-flow" />
          <rect x="206" y="76" width="28" height="10" rx="3" className="sim__pipe-cap" />
          <circle cx="120" cy="40" r="6" className="sim__crack" />
        </svg>
        <div className="sim__drops">
          {Array.from({ length: 5 }, (_, i) => (
            <span key={i} style={{ '--i': i } as CSSProperties} />
          ))}
        </div>
        <div className="sim__puddle" />
      </div>

      <div className="sim__controls">
        <label>
          <span>Süre</span>
          <input
            type="range"
            min={1}
            max={6}
            step={1}
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            disabled={running}
          />
          <b>{hours} saat</b>
        </label>
        <label>
          <span>Debi</span>
          <input
            type="range"
            min={6}
            max={40}
            step={2}
            value={rate}
            onChange={(e) => setRate(Number(e.target.value))}
            disabled={running}
          />
          <b>{rate} L/saat</b>
        </label>
        <button type="button" className="btn btn--danger" onClick={run} disabled={running}>
          {running ? (
            <>
              <span className="spinner" /> Model değerlendiriyor…
            </>
          ) : (
            'Kaçak simüle et'
          )}
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {result && (
        <div className="sim__results">
          <p className="sim__summary">{result.summary}</p>
          <ol>
            {result.results.map((r, i) => (
              <li key={r.timestamp_local} style={{ '--i': i } as CSSProperties}>
                <span className="sim__hour">{formatLocalTime(r.timestamp_local)}</span>
                <span className="sim__liters">{formatLiters(r.consumption_liters)}</span>
                <StatusBadge status={r.status} />
              </li>
            ))}
          </ol>
          <small className="muted">
            Tüketim verisine dokunulmaz; sonuçlar uyarı geçmişine “demo” etiketiyle eklenir. Gerçek bir
            kaçak teşhisi değildir.
          </small>
        </div>
      )}
    </section>
  );
}
