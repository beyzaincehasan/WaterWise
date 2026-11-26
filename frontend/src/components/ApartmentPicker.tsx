import type { ApartmentListItem } from '../api/types';

interface Props {
  apartments: ApartmentListItem[] | undefined;
  value: string;
  onChange: (id: string) => void;
}

/** Daire seçici: açılır liste ve önceki/sonraki daire okları. */
export function ApartmentPicker({ apartments, value, onChange }: Props) {
  const list = apartments ?? [];
  const index = list.findIndex((a) => a.id === value);
  const current = index >= 0 ? list[index] : undefined;

  const step = (dir: -1 | 1) => {
    if (list.length === 0) return;
    const next = (index + dir + list.length) % list.length;
    onChange(list[next].id);
  };

  return (
    <div className="picker">
      <button type="button" className="picker__arrow" onClick={() => step(-1)} aria-label="Önceki daire">
        ‹
      </button>
      <label className="picker__select">
        <span className="picker__label">Daire</span>
        <select value={value} onChange={(e) => onChange(e.target.value)} disabled={list.length === 0}>
          {list.length === 0 && <option>Yükleniyor…</option>}
          {list.map((a) => (
            <option key={a.id} value={a.id}>
              {a.id.replace('APT_', 'Daire ')}
            </option>
          ))}
        </select>
      </label>
      <button type="button" className="picker__arrow" onClick={() => step(1)} aria-label="Sonraki daire">
        ›
      </button>
      {current?.cluster_name && <span className="chip">Küme {current.cluster_name.replace('CL_', '')}</span>}
    </div>
  );
}
