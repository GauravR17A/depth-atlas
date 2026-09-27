import { RefreshCw } from 'lucide-react';
import { ApiError } from '../contracts';

export function AnalysisError({ error, retry }: { error: Error; retry: () => void }) {
  const reload = error instanceof ApiError && error.kind !== 'service';
  return <div className="p14-error" role="alert"><p><strong>{reload ? 'The response could not be verified.' : 'This calculation could not finish.'}</strong><br/>{error.message}</p><button className="secondary-button" onClick={reload ? () => window.location.reload() : retry}><RefreshCw size={15}/>{reload ? 'Reload workspace' : 'Try again'}</button></div>;
}
