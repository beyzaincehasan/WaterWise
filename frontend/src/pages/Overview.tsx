import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { ApartmentStatsResponse, DailyConsumptionItem } from '../api/types';
import { useAsync } from '../hooks/useAsync';
import { StatCard } from '../components/StatCard';
import { WaterDropGauge } from '../components/WaterDropGauge';
import { HourlyTimeline } from '../components/HourlyTimeline';
import { DailyChart } from '../components/DailyChart';
import { StatusBadge } from '../components/StatusBadge';
import { AlertBanner } from '../components/AlertBanner';
import { CalendarIcon, DropIcon, MoonIcon, PeakIcon } from '../components/Icons';
import { formatLiters, formatLongDate, formatNumber, STATUS_META, worstStatus } from '../utils/format';

interface Props {
  apartmentId: string;
  stats: ApartmentStatsResponse | undefined;
  daily: DailyConsumptionItem[] | undefined;
  onOpenAnomalies: () => void;
}

export function Overview({ apartmentId, stats, daily, onOpenAnomalies }: Props) {
  const lastDate = stats?.last_recorded_date ?? null;
  const [bannerOpen, setBannerOpen] = useState(true);

  const hourly = useAsync(
    () =>
      lastDate
        ? api.evaluateRange(apartmentId, `${lastDate}T00:00:00`, `${lastDate}T23:00:00`)
        : Promise.resolve([]),
    [apartmentId, lastDate],
  );

  useEffect(() => setBannerOpen(true), [apartmentId]);

  const dayStatus = hourly.data && hourly.data.length > 0 ? worstStatus(hourly.data.map((h) => h.status)) : null;
  const firstAlarm = hourly.data?.find((h) => h.status === 'Anormal');

  // Damla göstergesi: son günün tüketimi, dönem ortalamasına göre (ortalama = yarı dolu)
  const lastDay = daily && daily.length > 0 ? daily[daily.length - 1] : undefined;
  const mean = stats?.daily_mean_liters ?? 0;
  const ratio = lastDay && mean > 0 ? lastDay.total_liters / (mean * 2) : 0;
  const diffPct = lastDay && mean > 0 ? ((lastDay.total_liters - mean) / mean) * 100 : 0;
  const gaugeTone = diffPct > 60 ? 'alert' : diffPct > 25 ? 'warn' : 'ok';

  const recent = daily ? daily.slice(-14) : undefined;

  return (
    <div className="page">
      {firstAlarm && bannerOpen && (
        <AlertBanner
          title={`${apartmentId.replace('APT_', 'Daire ')} için kritik uyarı`}
          message={firstAlarm.message}
          disclaimer={firstAlarm.disclaimer}
          onClose={() => setBannerOpen(false)}
        />
      )}

      <section className="hero card">
        <div className="hero__text">
          <span className="eyebrow">Son kayıtlı gün · {lastDate ? formatLongDate(lastDate) : '…'}</span>
          <h1>
            {apartmentId.replace('APT_', 'Daire ')} su durumu{' '}
            {dayStatus && <StatusBadge status={dayStatus} size="lg" />}
          </h1>
          <p className="muted">
            {dayStatus
              ? STATUS_META[dayStatus].description
              : 'Yapay zekâ modeli son günün saatlerini değerlendiriyor…'}
          </p>
          {dayStatus && dayStatus !== 'Normal' && (
            <button type="button" className="btn btn--ghost" onClick={onOpenAnomalies}>
              Uyarı merkezine git →
            </button>
          )}
        </div>
        <WaterDropGauge
          ratio={ratio}
          value={lastDay?.total_liters ?? 0}
          unit="L"
          tone={gaugeTone}
          caption={
            lastDay
              ? `Son gün · ortalamanın %${formatNumber(Math.abs(diffPct), 0)} ${diffPct >= 0 ? 'üstünde' : 'altında'}`
              : 'Veri bekleniyor'
          }
        />
      </section>

      <section className="stats-grid">
        <StatCard
          index={0}
          icon={<DropIcon />}
          label="Toplam tüketim"
          value={stats?.total_consumption_liters}
          unit="L"
          digits={0}
          hint={
            stats?.first_recorded_date && stats.last_recorded_date
              ? `${formatLongDate(stats.first_recorded_date)} – ${formatLongDate(stats.last_recorded_date)}`
              : undefined
          }
        />
        <StatCard
          index={1}
          icon={<CalendarIcon />}
          label="Günlük ortalama"
          value={stats?.daily_mean_liters}
          unit="L/gün"
          hint={stats?.normal_daily_mean_liters != null ? `Profil ortalaması ${formatLiters(stats.normal_daily_mean_liters)}` : undefined}
        />
        <StatCard
          index={2}
          icon={<PeakIcon />}
          label="En yüksek saatlik"
          value={stats?.max_hourly_liters}
          unit="L/saat"
          hint="Dönemdeki tepe değer"
        />
        <StatCard
          index={3}
          icon={<MoonIcon />}
          label="Gece kullanımı"
          value={stats?.night_consumption_ratio}
          unit="%"
          hint="00:00 – 06:00 arası pay"
        />
      </section>

      <section className="card">
        <header className="card__head">
          <div>
            <h3>24 saatlik model taraması</h3>
            <p className="muted">Her sütun bir saat. Renk modelin kararını, çizgi normal üst sınırı gösterir.</p>
          </div>
          {hourly.data && (
            <div className="mini-legend">
              <span className="dot dot--ok" /> Normal
              <span className="dot dot--warn" /> Şüpheli
              <span className="dot dot--alert" /> Anormal
            </div>
          )}
        </header>
        {hourly.error ? <div className="error">{hourly.error}</div> : <HourlyTimeline data={hourly.data} loading={hourly.loading} />}
      </section>

      <section className="card">
        <header className="card__head">
          <div>
            <h3>Son 14 gün</h3>
            <p className="muted">Günlük toplam, soğuk ve sıcak su tüketimi</p>
          </div>
        </header>
        {recent ? <DailyChart data={recent} height={240} /> : <div className="skeleton skeleton--chart" />}
      </section>
    </div>
  );
}
