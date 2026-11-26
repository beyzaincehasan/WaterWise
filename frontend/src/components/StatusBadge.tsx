import type { AnomalyStatus } from '../api/types';
import { STATUS_META } from '../utils/format';

interface Props {
  status: AnomalyStatus;
  size?: 'sm' | 'lg';
}

/** Normal / Şüpheli / Anormal rozeti. Anormal durumda dalga halkaları yayılır. */
export function StatusBadge({ status, size = 'sm' }: Props) {
  const meta = STATUS_META[status];
  return (
    <span className={`badge badge--${meta.tone} badge--${size}`}>
      <span className="badge__dot">
        {meta.tone !== 'ok' && <span className="badge__ripple" />}
        {meta.tone === 'alert' && <span className="badge__ripple badge__ripple--late" />}
      </span>
      {meta.label}
    </span>
  );
}
