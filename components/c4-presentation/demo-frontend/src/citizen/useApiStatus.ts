import { useEffect, useState } from 'react';
import { GuidanceError, guidanceApi } from './api';
import type { ApiStatus } from './types';

export function useApiStatus() {
  const [status, setStatus] = useState<ApiStatus | null>(null), [error, setError] = useState('');
  useEffect(() => {
    const c = new AbortController();
    guidanceApi.status(c.signal).then(setStatus).catch(e => { if (!c.signal.aborted) setError(e instanceof GuidanceError ? e.message : 'The guidance service could not be reached.'); });
    return () => c.abort();
  }, []);
  return { status, error };
}
