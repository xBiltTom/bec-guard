import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { AuthProvider } from '../auth';
import { api, tokenKey } from '../api';
const user = {
  id: 'user-1',
  name: 'Lucía',
  role: 'ADMIN',
  email: 'lucia@example.com',
};
function renderApp(path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  );
}
export const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
describe('session', () => {
  it('protects routes and logs in using sessionStorage', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response({ access_token: 'test-token' }))
      .mockResolvedValueOnce(response(user));
    vi.stubGlobal('fetch', fetch);
    renderApp('/alerts');
    await userEvent.type(
      screen.getByLabelText('Correo electrónico'),
      user.email,
    );
    await userEvent.type(screen.getByLabelText('Contraseña'), 'test password');
    await userEvent.click(
      screen.getByRole('button', { name: 'Iniciar sesión' }),
    );
    await screen.findByText('Lucía');
    expect(sessionStorage.getItem(tokenKey)).toBe('test-token');
    expect(localStorage.length).toBe(0);
    expect(document.body.textContent).not.toContain('test-token');
    await userEvent.click(
      screen.getByRole('button', { name: 'Cerrar sesión' }),
    );
    expect(sessionStorage.getItem(tokenKey)).toBeNull();
  });
  it.each(['AUDITOR', 'ANALYST'])('navigation reflects %s', async (role) => {
    sessionStorage.setItem(tokenKey, 'test-token');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(response({ ...user, role })),
    );
    renderApp();
    await screen.findByText('Lucía');
    expect(!!screen.queryByRole('link', { name: 'Auditoría' })).toBe(
      role === 'AUDITOR',
    );
  });
  it('clears the session on authenticated 401', async () => {
    sessionStorage.setItem(tokenKey, 'test-token');
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response(user))
      .mockResolvedValue(response({}, 401));
    vi.stubGlobal('fetch', fetch);
    renderApp();
    await screen.findByText('Lucía');
    await expect(api('/emails')).rejects.toThrow();
    await screen.findByLabelText('Correo electrónico');
    expect(sessionStorage.getItem(tokenKey)).toBeNull();
  });
  it('keeps session on 403', async () => {
    sessionStorage.setItem(tokenKey, 'test-token');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({}, 403)));
    await expect(api('/audit')).rejects.toThrow('permisos');
    expect(sessionStorage.getItem(tokenKey)).toBe('test-token');
  });
  it('shows generic invalid credentials', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({}, 401)));
    renderApp('/login');
    await userEvent.type(
      screen.getByLabelText('Correo electrónico'),
      user.email,
    );
    await userEvent.type(screen.getByLabelText('Contraseña'), 'wrong');
    await userEvent.click(
      screen.getByRole('button', { name: 'Iniciar sesión' }),
    );
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Correo o contraseña incorrectos',
      ),
    );
  });
});
