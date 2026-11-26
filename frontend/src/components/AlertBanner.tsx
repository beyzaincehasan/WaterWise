import { AlertIcon, CloseIcon } from './Icons';

interface Props {
  title: string;
  message: string;
  disclaimer?: string;
  onClose: () => void;
}

/**
 * Kritik uyarı şeridi. API rehberine göre yalnızca status === "Anormal"
 * olduğunda gösterilir (Şüpheli durumlar sadece rozetle kalır).
 */
export function AlertBanner({ title, message, disclaimer, onClose }: Props) {
  return (
    <div className="alert-banner" role="alert">
      <span className="alert-banner__icon">
        <AlertIcon />
      </span>
      <div className="alert-banner__text">
        <strong>{title}</strong>
        <span>{message}</span>
        {disclaimer && <small>{disclaimer}</small>}
      </div>
      <button type="button" className="icon-btn" onClick={onClose} aria-label="Uyarıyı kapat">
        <CloseIcon />
      </button>
    </div>
  );
}
