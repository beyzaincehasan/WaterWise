import { useState } from 'react';
import type { DemoSimulateResponse } from '../api/types';
import { AnomalyFeed } from '../components/AnomalyFeed';
import { LeakSimulator } from '../components/LeakSimulator';
import { AlertBanner } from '../components/AlertBanner';

export function Anomalies({ apartmentId }: { apartmentId: string }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const [alarm, setAlarm] = useState<DemoSimulateResponse['results'][number] | null>(null);

  const handleDone = (res: DemoSimulateResponse) => {
    setRefreshKey((k) => k + 1);
    setAlarm(res.results.find((r) => r.status === 'Anormal') ?? null);
  };

  return (
    <div className="page">
      {alarm && (
        <AlertBanner
          title="Simülasyonda kritik uyarı üretildi"
          message={alarm.message}
          disclaimer={alarm.disclaimer}
          onClose={() => setAlarm(null)}
        />
      )}

      <section className="card info">
        <h3>Uyarılar nasıl üretiliyor?</h3>
        <div className="info__steps">
          <div>
            <span className="info__num">1</span>
            <p>Her saatin tüketimi, dairenin son 28 günlük alışkanlığıyla karşılaştırılır.</p>
          </div>
          <div>
            <span className="info__num">2</span>
            <p>Isolation Forest modeli saati Normal, Şüpheli veya Anormal olarak sınıflar.</p>
          </div>
          <div>
            <span className="info__num">3</span>
            <p>
              Yalnızca <b className="t-alert">Anormal</b> durumlar kritik uyarı üretir; şüpheli saatler rozetle
              izlenir.
            </p>
          </div>
        </div>
      </section>

      <div className="grid-2 grid-2--wide-right">
        <LeakSimulator apartmentId={apartmentId} onDone={handleDone} />
        <AnomalyFeed apartmentId={apartmentId} refreshKey={refreshKey} />
      </div>
    </div>
  );
}
