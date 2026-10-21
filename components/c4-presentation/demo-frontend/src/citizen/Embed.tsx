import { useEffect, useState } from 'react';
import { GuidanceError, guidanceApi } from './api';
import { guidanceIdentity } from './identity';
import { useJourney } from './useJourney';
import GuidanceCard from './card/GuidanceCard';
import type { ApiStatus } from './types';
import './citizen.css';

/**
 * Standalone Guidance Card for a 320-420 px chat container. No sidebar, no shell. It opens a guest session and
 * requests standard guidance for the procedure named in the address: #embed/<procedure_id>.
 */
export default function Embed({ procedureId }: { procedureId: string }) {
  const [session, setSession] = useState<string | null>(null), [status, setStatus] = useState<ApiStatus | null>(null), [error, setError] = useState('');
  useEffect(() => {
    let live = true;
    const key = 'c4-embed-session';
    const saved = (() => { try { return sessionStorage.getItem(key); } catch { return null; } })();
    guidanceApi.status().then(s => { if (live) setStatus(s); }).catch(() => undefined);
    (saved ? guidanceIdentity.getSession(saved).catch(() => guidanceIdentity.createSession()) : guidanceIdentity.createSession())
      .then(s => { if (live) { setSession(s.session_id); try { sessionStorage.setItem(key, s.session_id); } catch { /* storage unavailable */ } } })
      .catch(e => { if (live) setError(e instanceof GuidanceError ? e.message : 'The guidance service could not be reached.'); });
    return () => { live = false; };
  }, []);
  return <main className="cz-embed">{error ? <p className="cz-alert" role="alert">{error}</p> : session ? <EmbedCard sessionId={session} procedureId={procedureId} status={status} /> : <p className="cz-fine" role="status">Opening guidance…</p>}</main>;
}

function EmbedCard({ sessionId, procedureId, status }: { sessionId: string; procedureId: string; status: ApiStatus | null }) {
  const j = useJourney({ sessionId, procedureId, status });
  const { response, start } = j;
  useEffect(() => { if (!response && !j.busy && !j.error) void start({ kind: 'standard' }); }, [response, j.busy, j.error, start]);
  if (j.error) return <p className="cz-alert" role="alert">{j.error.message}</p>;
  return response ? <GuidanceCard response={response} emit={j.emit} busy={j.busy} /> : <p className="cz-fine" role="status">Preparing guidance…</p>;
}
