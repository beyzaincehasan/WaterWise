import { useMemo, useState, type CSSProperties } from 'react';
import { api } from '../api/client';
import type { DailyConsumptionItem } from '../api/types';
import { useAsync } from '../hooks/useAsync';
import { DailyChart } from '../components/DailyChart';
import { FixtureDonut } from '../components/FixtureDonut';
import { formatLiters, formatLongDate, formatNumber } from '../utils/format';

type Range = 7 | 14 | 'all';

interface Props {
  apartmentId: string;
  daily: DailyConsumptionItem[] | undefined;
  dailyError?: string;
}

export function Consumption({ apartmentId, daily, dailyError }: Props) {
  const [range, setRange] = useState<Range>('all');

  const shown = useMemo(() => {
    if (!daily) return undefined;
    return range === 'all' ? daily : daily.slice(-range);
  }, [daily, range]);

  const startDate = shown && shown.length > 0 ? shown[0].date : undefined;
  const endDate = shown && shown.length > 0 ? shown[shown.length - 1].date : undefined;

  const fixtures = useAsync(
    () => api.fixtureBreakdown(apartmentId, startDate, endDate),
    [apartmentId, startDate, endDate],
  );

  const totals = useMemo(() => {
    const list = shown ?? [];
    const cold = list.reduce((s, d) => s + d.cold_water_liters, 0);
    const hot = list.reduce((s, d) => s + d.hot_water_liters, 0);
    const total = cold + hot;
    const peak = list.reduce<DailyConsumptionItem | null>(
      (best, d) => (!best || d.total_liters > best.total_liters ? d : best),
      null,
    );
    const calm = list.reduce<DailyConsumptionItem | null>(
      (best, d) => (!best || d.total_liters < best.total_liters ? d : best),
      null,
    );
    return { cold, hot, total, peak, calm };
  }, [shown]);

  const coldPct = totals.total > 0 ? (totals.cold / totals.total) * 100 : 50;

  return (
    <div className="page">
      <section className="card">
        <header className="card__head">
          <div>
            <h3>Günlük tüketim</h3>
            <p className="muted">
              {startDate && endDate ? `${formatLongDate(startDate)} – ${formatLongDate(endDate)}` : 'Yükleniyor…'}
            </p>
          </div>
          <div className="segmented">
            {([7, 14, 'all'] as Range[]).map((r) => (
              <button
                key={String(r)}
                type="button"
                className={range === r ? 'is-active' : ''}
                onClick={() => setRange(r)}
              >
                {r === 'all' ? 'Tümü' : `Son ${r} gün`}
              </button>
            ))}
          </div>
        </header>
        {dailyError ? (
          <div className="error">{dailyError}</div>
        ) : shown ? (
          <DailyChart data={shown} />
        ) : (
          <div className="skeleton skeleton--chart" />
        )}
      </section>

      <div className="grid-2">
        <section className="card">
          <header className="card__head">
            <div>
              <h3>Su nereye gidiyor?</h3>
              <p className="muted">Armatür bazında kullanım dağılımı</p>
            </div>
          </header>
          {fixtures.error ? (
            <div className="error">{fixtures.error}</div>
          ) : fixtures.data ? (
            <FixtureDonut data={fixtures.data} />
          ) : (
            <div className="skeleton skeleton--donut" />
          )}
        </section>

        <section className="card temp">
          <header className="card__head">
            <div>
              <h3>Soğuk ve sıcak su</h3>
              <p className="muted">Seçili dönemin toplamı</p>
            </div>
          </header>

          <div className="temp__bar" style={{ '--cold': `${coldPct}%` } as CSSProperties}>
            <span className="temp__cold" />
            <span className="temp__hot" />
          </div>
          <div className="temp__labels">
            <div>
              <span className="t-cold">❄ Soğuk</span>
              <strong>{formatLiters(totals.cold, 0)}</strong>
              <small>%{formatNumber(coldPct, 0)}</small>
            </div>
            <div className="right">
              <span className="t-hot">♨ Sıcak</span>
              <strong>{formatLiters(totals.hot, 0)}</strong>
              <small>%{formatNumber(100 - coldPct, 0)}</small>
            </div>
          </div>

          <dl className="facts facts--stack">
            <div>
              <dt>En yoğun gün</dt>
              <dd>
                {totals.peak ? `${formatLongDate(totals.peak.date)} · ${formatLiters(totals.peak.total_liters)}` : '—'}
              </dd>
            </div>
            <div>
              <dt>En sakin gün</dt>
              <dd>
                {totals.calm ? `${formatLongDate(totals.calm.date)} · ${formatLiters(totals.calm.total_liters)}` : '—'}
              </dd>
            </div>
            <div>
              <dt>Dönem toplamı</dt>
              <dd>{formatLiters(totals.total, 0)}</dd>
            </div>
          </dl>

          <p className="tip">
            💡 Duşu 1 dakika kısaltmak, günde yaklaşık 8–10 litre tasarruf sağlar.
          </p>
        </section>
      </div>
    </div>
  );
}
