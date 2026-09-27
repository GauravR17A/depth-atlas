import { StrictMode, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from './App';
import { ApiError } from './contracts';
import './styles.css';
import './workspace/workspace.css';

const queryClient = new QueryClient({ defaultOptions: { queries: {
  retry: (attempt, error) => attempt < 1 && !(error instanceof ApiError && error.kind !== 'service'),
  staleTime: 30_000,
  refetchOnWindowFocus: false,
} } });

function StartupReady() {
  useEffect(() => { window.dispatchEvent(new Event('ocean:mounted')); }, []);
  return null;
}

createRoot(document.getElementById('root')!).render(
  <StrictMode><QueryClientProvider client={queryClient}><App /><StartupReady /></QueryClientProvider></StrictMode>,
);
