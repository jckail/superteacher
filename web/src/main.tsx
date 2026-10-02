import React, { useCallback, useRef, useState } from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { ThemeProvider } from './theme';
import { AuthGate, clearPrivateSession } from './auth';
import './styles.css';

function createQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { staleTime: 15_000, retry: 1, refetchOnWindowFocus: false } } });
}

export function Root({ children }: { children?: React.ReactNode }) {
  const [client, setClient] = useState(createQueryClient);
  const currentClient = useRef(client);
  const resetSession = useCallback(() => {
    clearPrivateSession(currentClient.current);
    // Requests already in flight keep their old client, isolated from the next session.
    const nextClient = createQueryClient();
    currentClient.current = nextClient;
    setClient(nextClient);
  }, []);

  return (
    <QueryClientProvider client={client}>
      <ThemeProvider><AuthGate onLogout={resetSession}>
        {children ?? <BrowserRouter><App /></BrowserRouter>}
      </AuthGate></ThemeProvider>
    </QueryClientProvider>
  );
}

const root = document.getElementById('root');
if (!root) throw new Error('Application root is missing');
ReactDOM.createRoot(root).render(<React.StrictMode><Root /></React.StrictMode>);
