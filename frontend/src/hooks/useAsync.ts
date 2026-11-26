import { useCallback, useEffect, useState, type DependencyList } from 'react';

interface AsyncState<T> {
  data: T | undefined;
  error: string | undefined;
  loading: boolean;
}

/**
 * Basit veri çekme kancası. Bağımlılıklar değişince isteği tekrarlar,
 * yeniden yüklenirken eski veriyi ekranda tutar (titreme olmasın diye).
 */
export function useAsync<T>(fn: () => Promise<T>, deps: DependencyList) {
  const [state, setState] = useState<AsyncState<T>>({
    data: undefined,
    error: undefined,
    loading: true,
  });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    setState((prev) => ({ ...prev, loading: true, error: undefined }));
    fn()
      .then((data) => {
        if (alive) setState({ data, error: undefined, loading: false });
      })
      .catch((err: unknown) => {
        if (alive) {
          setState((prev) => ({
            data: prev.data,
            error: err instanceof Error ? err.message : String(err),
            loading: false,
          }));
        }
      });
    return () => {
      alive = false;
    };
    // fn her render'da yeni oluşur; tetikleyici olarak yalnızca deps ve tick kullanılır.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  return { ...state, reload };
}
