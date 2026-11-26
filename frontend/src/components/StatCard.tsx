import type { CSSProperties, ReactNode } from 'react';
import { useCountUp } from '../hooks/useCountUp';
import { formatNumber } from '../utils/format';

interface Props {
  label: string;
  value: number | undefined;
  unit: string;
  icon: ReactNode;
  hint?: ReactNode;
  digits?: 0 | 1;
  index?: number;
}

export function StatCard({ label, value, unit, icon, hint, digits = 1, index = 0 }: Props) {
  const animated = useCountUp(value ?? 0);
  return (
    <article className="card stat" style={{ '--i': index } as CSSProperties}>
      <div className="stat__icon">{icon}</div>
      <div className="stat__body">
        <span className="stat__label">{label}</span>
        <span className="stat__value">
          {value === undefined ? <span className="skeleton skeleton--text" /> : formatNumber(animated, digits)}
          <small>{unit}</small>
        </span>
        {hint && <span className="stat__hint">{hint}</span>}
      </div>
      <span className="stat__shine" />
    </article>
  );
}
