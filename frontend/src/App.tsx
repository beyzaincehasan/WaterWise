import { useEffect, useState, type ReactNode } from 'react';
import { api } from './api/client';
import { useAsync } from './hooks/useAsync';
import { OceanBackground } from './components/OceanBackground';
import { Logo } from './components/Logo';
import { ApartmentPicker } from './components/ApartmentPicker';
import { ChartIcon, ShieldIcon, WaveIcon } from './components/Icons';
import { Overview } from './pages/Overview';
import { Consumption } from './pages/Consumption';
import { Anomalies } from './pages/Anomalies';

type Tab = 'overview' | 'consumption' | 'anomalies';

const TABS: { id: Tab; label: string; icon: ReactNode }[] = [
  { id: 'overview', label: 'Genel Bakış', icon: <WaveIcon /> },
  { id: 'consumption', label: 'Tüketim Analizi', icon: <ChartIcon /> },
  { id: 'anomalies', label: 'Uyarı Merkezi', icon: <ShieldIcon /> },
];

const DEFAULT_APARTMENT = 'APT_011';

export default function App() {
  const [tab, setTab] = useState<Tab>('overview');
  const [apartmentId, setApartmentId] = useState(DEFAULT_APARTMENT);

  const health = useAsync(() => api.health(), []);
  const apartments = useAsync(() => api.apartments(), []);
  const stats = useAsync(() => api.stats(apartmentId), [apartmentId]);
  const daily = useAsync(() => api.dailyConsumption(apartmentId), [apartmentId]);

  // Varsayılan daire listede yoksa ilk daireye geç
  useEffect(() => {
    const list = apartments.data;
    if (list && list.length > 0 && !list.some((a) => a.id === apartmentId)) {
      setApartmentId(list[0].id);
    }
  }, [apartments.data, apartmentId]);

  const online = health.data?.status === 'healthy';
  const backendDown = Boolean(health.error);

  return (
    <>
      <OceanBackground />

      <div className="shell">
        <header className="topbar">
          <div className="brand">
            <Logo size={42} />
            <div>
              <span className="brand__name">WaterWise</span>
              <span className="brand__tag">Yapay zekâ destekli su tüketimi analizi</span>
            </div>
          </div>

          <nav className="tabs" aria-label="Sayfalar">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                className={`tabs__item ${tab === t.id ? 'is-active' : ''}`}
                onClick={() => setTab(t.id)}
              >
                {t.icon}
                <span>{t.label}</span>
              </button>
            ))}
          </nav>

          <div className={`health ${online ? 'is-online' : backendDown ? 'is-offline' : ''}`}>
            <span className="health__dot" />
            {online
              ? `Model v${health.data?.model_version} · ${health.data?.known_apartments_count} daire`
              : backendDown
                ? 'Backend kapalı'
                : 'Bağlanıyor…'}
          </div>
        </header>

        {backendDown && (
          <div className="error error--big">
            <strong>Backend’e bağlanılamadı.</strong> Terminalde{' '}
            <code>python -m uvicorn backend.app.main:app --reload --port 8000</code> komutunun çalıştığından emin
            ol, sonra sayfayı yenile.
          </div>
        )}

        <div className="toolbar">
          <ApartmentPicker apartments={apartments.data} value={apartmentId} onChange={setApartmentId} />
        </div>

        <main key={tab} className="page-transition">
          {tab === 'overview' && (
            <Overview
              apartmentId={apartmentId}
              stats={stats.data}
              daily={daily.data}
              onOpenAnomalies={() => setTab('anomalies')}
            />
          )}
          {tab === 'consumption' && (
            <Consumption apartmentId={apartmentId} daily={daily.data} dailyError={daily.error} />
          )}
          {tab === 'anomalies' && <Anomalies apartmentId={apartmentId} />}
        </main>

        <footer className="footer">
          <span>💧 WaterWise · Sosyal sorumluluk projesi</span>
          <span className="muted">
            Uyarılar tüketim davranışına dayanır; kesin tesisat kaçağı teşhisi değildir.
          </span>
        </footer>
      </div>
    </>
  );
}
