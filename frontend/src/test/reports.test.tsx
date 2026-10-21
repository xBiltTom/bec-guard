import type { Mock } from 'vitest';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { AuthProvider } from '../auth';
import { authenticatedDownload, tokenKey } from '../api';
import { user, response } from './fixtures';
import type { Role } from '../types';
let created: ReturnType<typeof vi.fn>;
let revoked: ReturnType<typeof vi.fn>;
let clicked: Mock<(filename: string) => void>;
beforeEach(() => {
  created = vi.fn(() => 'blob:report');
  revoked = vi.fn();
  clicked = vi.fn<(filename: string) => void>();
  Object.defineProperty(URL, 'createObjectURL', {
    value: created,
    writable: true,
    configurable: true,
  });
  Object.defineProperty(URL, 'revokeObjectURL', {
    value: revoked,
    writable: true,
    configurable: true,
  });
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    clicked(this.download);
  });
});
afterEach(() => vi.restoreAllMocks());
function setup(role: Role = 'ADMIN', status = 200) {
  sessionStorage.setItem(tokenKey, 'test-token');
  const fetch = vi.fn((url: string) =>
    Promise.resolve(
      url.endsWith('/auth/me')
        ? response({ ...user, role })
        : status === 200
          ? new Response('artifact', {
              status: 200,
              headers: {
                'Content-Disposition': `attachment; filename="bec-guard-operational-20261021.${url.includes('.xlsx') ? 'xlsx' : 'pdf'}"`,
              },
            })
          : response({}, status),
    ),
  );
  vi.stubGlobal('fetch', fetch);
  render(
    <MemoryRouter initialEntries={['/reports']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  );
  return fetch;
}
it.each(['ADMIN', 'MANAGER', 'AUDITOR'] as const)(
  'reports visible to %s',
  async (role) => {
    setup(role);
    await screen.findByRole('heading', { name: 'Reporte operativo' });
    expect(screen.getByRole('link', { name: 'Reportes' })).toBeInTheDocument();
  },
);
it('analyst has no reports link or download controls', async () => {
  const fetch = setup('ANALYST');
  await screen.findByRole('alert');
  expect(
    screen.queryByRole('link', { name: 'Reportes' }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: 'Descargar PDF' }),
  ).not.toBeInTheDocument();
  expect(fetch.mock.calls.some(([url]) => url.includes('/reports/'))).toBe(
    false,
  );
});
it.each([
  ['Descargar PDF', 'pdf'],
  ['Descargar Excel', 'xlsx'],
])('authenticated %s download and cleanup', async (button, extension) => {
  const fetch = setup();
  await userEvent.click(await screen.findByRole('button', { name: button }));
  await screen.findByText('Descarga preparada.');
  const call = fetch.mock.calls.find(([url]) => url.includes('/reports/'));
  expect(call?.[0]).toBe('/api/reports/operational.' + extension);
  expect(created).toHaveBeenCalledOnce();
  expect(clicked).toHaveBeenCalledWith(
    'bec-guard-operational-20261021.' + extension,
  );
  expect(revoked).toHaveBeenCalledWith('blob:report');
  expect(document.querySelector('a[download]')).toBeNull();
});
it('sends Bearer and dates without exposing the token', async () => {
  sessionStorage.setItem(tokenKey, 'test-token');
  const fetch = vi.fn().mockResolvedValue(
    new Response('artifact', {
      headers: {
        'Content-Disposition': 'attachment; filename="../unsafe.pdf"',
      },
    }),
  );
  vi.stubGlobal('fetch', fetch);
  await authenticatedDownload(
    '/reports/operational.pdf?from_date=2026-10-01&to_date=2026-10-21',
  );
  expect(fetch).toHaveBeenCalledWith(
    '/api/reports/operational.pdf?from_date=2026-10-01&to_date=2026-10-21',
    expect.objectContaining({
      headers: { Authorization: 'Bearer test-token' },
    }),
  );
  expect(clicked).toHaveBeenCalledWith('bec-guard-operational.pdf');
  expect(document.body.textContent).not.toContain('test-token');
});
it('invalid range disables both download buttons', async () => {
  const fetch = setup();
  await screen.findByLabelText('Fecha desde');
  await userEvent.type(screen.getByLabelText('Fecha desde'), '2026-10-22');
  await userEvent.type(screen.getByLabelText('Fecha hasta'), '2026-10-21');
  expect(screen.getByRole('alert')).toHaveTextContent('anterior o igual');
  expect(screen.getByRole('button', { name: 'Descargar PDF' })).toBeDisabled();
  expect(
    screen.getByRole('button', { name: 'Descargar Excel' }),
  ).toBeDisabled();
  expect(fetch.mock.calls.some(([url]) => url.includes('/reports/'))).toBe(
    false,
  );
});
it.each([403, 503])(
  'download HTTP %s displays feedback and retains session',
  async (status) => {
    setup('ADMIN', status);
    await userEvent.click(
      await screen.findByRole('button', { name: 'Descargar PDF' }),
    );
    await screen.findByRole('alert');
    expect(sessionStorage.getItem(tokenKey)).toBe('test-token');
    expect(created).not.toHaveBeenCalled();
  },
);
it('download 401 logs out', async () => {
  setup('ADMIN', 401);
  await userEvent.click(
    await screen.findByRole('button', { name: 'Descargar PDF' }),
  );
  await screen.findByLabelText('Correo electrónico');
  expect(sessionStorage.getItem(tokenKey)).toBeNull();
});
it('pending download disables actions', async () => {
  sessionStorage.setItem(tokenKey, 't');
  let finish: (r: Response) => void = () => {};
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      url.endsWith('/auth/me')
        ? Promise.resolve(response({ ...user, role: 'ADMIN' }))
        : new Promise<Response>((resolve) => {
            finish = resolve;
          }),
    ),
  );
  render(
    <MemoryRouter initialEntries={['/reports']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Descargar PDF' }),
  );
  expect(screen.getByRole('button', { name: 'Generando PDF…' })).toBeDisabled();
  expect(
    screen.getByRole('button', { name: 'Descargar Excel' }),
  ).toBeDisabled();
  finish(new Response('pdf'));
  await waitFor(() => expect(revoked).toHaveBeenCalled());
});
