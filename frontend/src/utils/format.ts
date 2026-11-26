import type { AnomalyStatus } from '../api/types';

const nf1 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 });
const nf0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });

export const formatLiters = (value: number | null | undefined, digits: 0 | 1 = 1): string =>
  value === null || value === undefined ? '—' : `${(digits === 0 ? nf0 : nf1).format(value)} L`;

export const formatNumber = (value: number, digits: 0 | 1 = 1): string =>
  (digits === 0 ? nf0 : nf1).format(value);

const MONTHS = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'];

/** "2022-11-01" → "1 Kas" (tarayıcı saat dilimine dokunmadan) */
export function formatShortDate(isoDate: string): string {
  const [, month, day] = isoDate.slice(0, 10).split('-');
  return `${Number(day)} ${MONTHS[Number(month) - 1] ?? ''}`;
}

/** "2022-11-01" → "1 Kas 2022" */
export function formatLongDate(isoDate: string): string {
  return `${formatShortDate(isoDate)} ${isoDate.slice(0, 4)}`;
}

/**
 * Backend'in hazır verdiği yerel saat ("2022-11-24T03:00:00+01:00") alanından
 * duvar saatini okur. Tarayıcı kendi saat dilimine çevirmesin diye Date kullanılmaz.
 */
export function formatLocalTime(localIso: string): string {
  return localIso.slice(11, 16);
}

export function formatLocalDateTime(localIso: string): string {
  return `${formatShortDate(localIso)} · ${formatLocalTime(localIso)}`;
}

export const STATUS_META: Record<
  AnomalyStatus,
  { tone: 'ok' | 'warn' | 'alert'; label: string; color: string; description: string }
> = {
  Normal: {
    tone: 'ok',
    label: 'Normal',
    color: 'var(--ok)',
    description: 'Tüketim dairenin olağan alışkanlıklarıyla uyumlu.',
  },
  Şüpheli: {
    tone: 'warn',
    label: 'Şüpheli',
    color: 'var(--warn)',
    description: 'Normalden belirli bir sapma var, gözlemde tutuluyor.',
  },
  Anormal: {
    tone: 'alert',
    label: 'Anormal',
    color: 'var(--alert)',
    description: 'Belirgin olağandışı tüketim. Kontrol önerilir.',
  },
};

const SEVERITY: Record<AnomalyStatus, number> = { Normal: 0, Şüpheli: 1, Anormal: 2 };

export function worstStatus(statuses: AnomalyStatus[]): AnomalyStatus {
  return statuses.reduce<AnomalyStatus>(
    (worst, s) => (SEVERITY[s] > SEVERITY[worst] ? s : worst),
    'Normal',
  );
}
