import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { api, tokenKey } from './api';
import type { User } from './types';

interface Session {
  user: User | null;
  loading: boolean;
  error: string;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  retry: () => void;
}
const AuthContext = createContext<Session | null>(null);
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(!!sessionStorage.getItem(tokenKey));
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const clear = () => {
      setUser(null);
      setError('');
      setLoading(false);
    };
    window.addEventListener('bec-session-expired', clear);
    if (sessionStorage.getItem(tokenKey)) {
      api<User>('/auth/me', { signal: controller.signal })
        .then(setUser)
        .catch((e: unknown) => {
          if (!controller.signal.aborted && sessionStorage.getItem(tokenKey))
            setError(
              e instanceof Error
                ? e.message
                : 'No se pudo verificar la sesión.',
            );
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }
    return () => {
      controller.abort();
      window.removeEventListener('bec-session-expired', clear);
    };
  }, [attempt]);
  async function login(email: string, password: string) {
    const result = await api<{ access_token: string }>(
      '/auth/login',
      { method: 'POST', body: JSON.stringify({ email, password }) },
      null,
    );
    const current = await api<User>('/auth/me', {}, result.access_token);
    sessionStorage.setItem(tokenKey, result.access_token);
    setUser(current);
    setError('');
  }
  function logout() {
    sessionStorage.removeItem(tokenKey);
    setUser(null);
    setError('');
  }
  return (
    <AuthContext
      value={{
        user,
        loading,
        error,
        login,
        logout,
        retry: () => {
          setLoading(true);
          setError('');
          setAttempt((a) => a + 1);
        },
      }}
    >
      {children}
    </AuthContext>
  );
}
export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('AuthProvider required');
  return value;
}
