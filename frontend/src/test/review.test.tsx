import { it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { AuthProvider } from '../auth';
import { tokenKey } from '../api';
import { alert, email, user, dashboard, summary, response } from './fixtures';
import type { AlertDetail, Role } from '../types';
function setup(
  path = '/',
  role: Role = 'ANALYST',
  initial: AlertDetail = alert,
  conflict = false,
) {
  sessionStorage.setItem(tokenKey, 'test-token');
  let current = structuredClone(initial);
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/auth/me')) return response({ ...user, role });
    if (url.includes('/dashboard/')) return response(dashboard);
    if (url === '/api/alerts?limit=5') return response([summary]);
    if (url.startsWith('/api/alerts?')) return response([summary]);
    if (url === '/api/emails/email-1') return response(email);
    if (url === '/api/alerts/alert-1') return response(current);
    if (url.endsWith('/claim')) {
      if (conflict) {
        current = {
          ...current,
          status: 'UNDER_REVIEW',
          assigned_to: 'other',
          assigned_to_name: 'Otra persona',
        };
        return response({}, 409);
      }
      current = {
        ...current,
        status: 'UNDER_REVIEW',
        assigned_to: user.id,
        assigned_to_name: user.name,
      };
      return response(current);
    }
    if (url.endsWith('/release')) {
      current = { ...current, status: 'OPEN', assigned_to: null };
      return response(current);
    }
    if (url.endsWith('/resolve')) {
      const body = JSON.parse(String(init?.body));
      current = {
        ...current,
        status: 'CLOSED',
        verdict: body.verdict,
        resolution: body.resolution,
        closed_at: '2026-10-21T14:00:00Z',
      };
      return response(current);
    }
    return response({}, 404);
  });
  vi.stubGlobal('fetch', fetch);
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  );
  return fetch;
}
it('dashboard displays real aggregates and recent links', async () => {
  setup();
  await screen.findByText('Correos recibidos');
  expect(screen.getByText('12')).toBeInTheDocument();
  expect(
    await screen.findByRole('link', { name: email.subject }),
  ).toHaveAttribute('href', '/alerts/alert-1');
});
it('dashboard error is actionable', async () => {
  sessionStorage.setItem(tokenKey, 't');
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve(
        url.endsWith('/auth/me') ? response(user) : response({}, 503),
      ),
    ),
  );
  render(
    <MemoryRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  );
  await screen.findByRole('alert');
  expect(
    screen.getByRole('button', { name: 'Reintentar' }),
  ).toBeInTheDocument();
});
it('alert filters request backend filters', async () => {
  const fetch = setup('/alerts');
  await screen.findByRole('link', { name: email.subject });
  await userEvent.selectOptions(
    screen.getByLabelText('Estado'),
    'UNDER_REVIEW',
  );
  await waitFor(() =>
    expect(
      fetch.mock.calls.some(([url]) => url.includes('status=UNDER_REVIEW')),
    ).toBe(true),
  );
  await userEvent.selectOptions(screen.getByLabelText('Riesgo'), 'HIGH');
  await userEvent.selectOptions(
    screen.getByLabelText('Tipo BEC'),
    'BANK_ACCOUNT_CHANGE',
  );
  await userEvent.click(screen.getByLabelText('Mis alertas'));
  await waitFor(() =>
    expect(
      fetch.mock.calls.some(([url]) => url.includes('assigned_to=user-1')),
    ).toBe(true),
  );
});
it('alert queue has loading and empty states', async () => {
  sessionStorage.setItem(tokenKey, 't');
  let finish: (r: Response) => void = () => {};
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      url.endsWith('/auth/me')
        ? Promise.resolve(response(user))
        : new Promise<Response>((resolve) => {
            finish = resolve;
          }),
    ),
  );
  render(
    <MemoryRouter initialEntries={['/alerts']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  );
  await screen.findByRole('heading', { name: 'Alertas' });
  expect(screen.getByRole('status')).toHaveTextContent('Cargando');
  finish(response([]));
  await screen.findByText('No hay alertas con estos filtros.');
});
it('detail safely renders email and separates signals', async () => {
  setup('/alerts/alert-1');
  await screen.findByText(
    (_, element) =>
      element?.tagName === 'PRE' && element.textContent === email.body_text,
  );
  expect(screen.getByText('Análisis semántico')).toBeInTheDocument();
  expect(screen.queryByText('+0 puntos deterministas')).not.toBeInTheDocument();
  expect(document.querySelector('.email-body script')).toBeNull();
  expect(document.querySelector('.email-body a')).toBeNull();
});
it.each(['CONFIRMED_BEC', 'FALSE_POSITIVE'] as const)(
  'claim and resolve %s',
  async (verdict) => {
    const fetch = setup('/alerts/alert-1');
    await userEvent.click(
      await screen.findByRole('button', { name: 'Tomar revisión' }),
    );
    await screen.findByText('En revisión por ti');
    await userEvent.click(
      screen.getByRole('button', {
        name:
          verdict === 'CONFIRMED_BEC'
            ? 'Confirmar BEC'
            : 'Marcar falso positivo',
      }),
    );
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await userEvent.type(
      screen.getByLabelText('Resolución'),
      'Identidad verificada fuera del correo.',
    );
    await userEvent.click(
      screen.getByRole('button', { name: 'Confirmar decisión' }),
    );
    await screen.findByText('Decisión final registrada en auditoría.');
    expect(
      screen.queryByRole('button', { name: 'Tomar revisión' }),
    ).not.toBeInTheDocument();
    expect(
      fetch.mock.calls.some(
        ([url, options]) =>
          url.endsWith('/resolve') && String(options?.body).includes(verdict),
      ),
    ).toBe(true);
  },
);
it('release returns to OPEN', async () => {
  setup('/alerts/alert-1', 'ANALYST', {
    ...alert,
    status: 'UNDER_REVIEW',
    assigned_to: user.id,
  });
  await userEvent.click(
    await screen.findByRole('button', { name: 'Liberar revisión' }),
  );
  await screen.findByRole('button', { name: 'Tomar revisión' });
});
it('409 refreshes current ownership', async () => {
  setup('/alerts/alert-1', 'ANALYST', alert, true);
  await userEvent.click(
    await screen.findByRole('button', { name: 'Tomar revisión' }),
  );
  await screen.findByText('En revisión por Otra persona');
  expect(screen.getByText(/La alerta cambió durante/)).toBeInTheDocument();
});
it('auditor sees no mutation actions', async () => {
  setup('/alerts/alert-1', 'AUDITOR');
  await screen.findByRole('heading', { name: 'Revisión humana' });
  expect(
    screen.queryByRole('button', { name: 'Tomar revisión' }),
  ).not.toBeInTheDocument();
});
it('analyst cannot act on someone else review', async () => {
  setup('/alerts/alert-1', 'ANALYST', {
    ...alert,
    status: 'UNDER_REVIEW',
    assigned_to: 'other',
    assigned_to_name: 'Otra persona',
  });
  await screen.findByText('En revisión por Otra persona');
  expect(
    screen.queryByRole('button', { name: 'Confirmar BEC' }),
  ).not.toBeInTheDocument();
});
