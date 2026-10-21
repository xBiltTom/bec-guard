import { it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { AuthProvider } from '../auth';
import { tokenKey } from '../api';
import type { Role } from '../types';
import { alert, email, user, response, summary } from './fixtures';
const executive = {
  id: 'executive-1',
  name: 'Nora Prisma',
  position: 'Directora',
  department: 'Dirección',
  email: 'nora@official.example',
  is_active: true,
};
const vendor = {
  id: 'vendor-1',
  name: 'Atlas Logística',
  domain: 'atlas.example',
  contact_email: 'contact@atlas.example',
  bank_account_reference: 'PRIVATE-BANK-REFERENCE',
  is_active: true,
};
function setup(
  path: string,
  role: Role = 'ADMIN',
  options: {
    empty?: boolean;
    analysis?: 'missing' | 'error' | 'completed';
    auditError?: boolean;
  } = {},
) {
  sessionStorage.setItem(tokenKey, 't');
  let analysis =
    options.analysis === 'completed'
      ? alert.analysis
      : options.analysis === 'error'
        ? {
            ...alert.analysis,
            status: 'ERROR',
            risk_score: null,
            risk_level: null,
            error_code: 'LLM_TIMEOUT',
          }
        : null;
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/auth/me')) return response({ ...user, role });
    if (url.includes('/audit?'))
      return options.auditError
        ? response({}, 403)
        : response(
            options.empty
              ? []
              : [
                  {
                    id: 'event-1',
                    actor_name: 'Lucía',
                    actor_user_id: user.id,
                    actor_role: role,
                    action: 'BEC_ALERT_CONFIRMED',
                    resource_type: 'bec_alert',
                    resource_id: alert.id,
                    created_at: '2026-10-21T15:00:00Z',
                    ip_address: '127.0.0.1',
                    details: null,
                  },
                ],
          );
    if (url === '/api/emails/email-1/analysis')
      return analysis ? response(analysis) : response({}, 404);
    if (url.endsWith('/analyze')) {
      analysis = alert.analysis;
      return response(analysis);
    }
    if (url.startsWith('/api/alerts?')) return response([summary]);
    if (url === '/api/emails/email-1') return response(email);
    if (url.startsWith('/api/emails?'))
      return response(options.empty ? [] : [email]);
    if (url.startsWith('/api/executives'))
      return response(
        init?.method ? executive : options.empty ? [] : [executive],
      );
    if (url.startsWith('/api/vendors'))
      return response(init?.method ? vendor : options.empty ? [] : [vendor]);
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
it('email list links to safe detail', async () => {
  setup('/emails');
  const link = await screen.findByRole('link', { name: email.subject });
  expect(link).toHaveAttribute('href', '/emails/email-1');
  expect(screen.queryByText(email.body_text)).not.toBeInTheDocument();
  await userEvent.click(link);
  await screen.findByRole('heading', { name: 'Correo original' });
  expect(document.querySelector('.email-body script')).toBeNull();
});
it.each(['ADMIN', 'MANAGER', 'ANALYST', 'AUDITOR'] as const)(
  'manual analysis permissions %s',
  async (role) => {
    setup('/emails/email-1', role);
    await screen.findByRole('heading', { name: 'Sin análisis' });
    expect(!!screen.queryByRole('button', { name: 'Analizar correo' })).toBe(
      role !== 'AUDITOR',
    );
    if (role !== 'AUDITOR') {
      await userEvent.click(
        screen.getByRole('button', { name: 'Analizar correo' }),
      );
      await screen.findByText(alert.analysis.summary!);
      await screen.findByRole('link', { name: 'Abrir alerta asociada' });
    }
  },
);
it('retry ERROR updates the persisted analysis', async () => {
  const fetch = setup('/emails/email-1', 'ANALYST', { analysis: 'error' });
  await screen.findByText('LLM_TIMEOUT');
  await userEvent.click(
    screen.getByRole('button', { name: 'Reintentar análisis' }),
  );
  await screen.findByText(alert.analysis.summary!);
  expect(
    fetch.mock.calls.some(
      ([url, init]) => url.endsWith('/analyze') && init?.method === 'POST',
    ),
  ).toBe(true);
});
it('provider ERROR is displayed after manual attempt', async () => {
  sessionStorage.setItem(tokenKey, 't');
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve(
        url.endsWith('/auth/me')
          ? response(user)
          : url.endsWith('/analysis')
            ? response({}, 404)
            : url.endsWith('/analyze')
              ? response(
                  {
                    ...alert.analysis,
                    status: 'ERROR',
                    risk_score: null,
                    risk_level: null,
                    error_code: 'LLM_NOT_CONFIGURED',
                  },
                  503,
                )
              : response(email),
      ),
    ),
  );
  render(
    <MemoryRouter initialEntries={['/emails/email-1']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Analizar correo' }),
  );
  await screen.findByText('LLM_NOT_CONFIGURED');
  expect(screen.queryByText('Bajo')).not.toBeInTheDocument();
});
it.each(['executives', 'vendors'] as const)(
  'context %s supports persisted create edit and activation',
  async (kind) => {
    const fetch = setup('/' + kind);
    await screen.findByText(
      kind === 'executives' ? executive.name : vendor.name,
    );
    expect(
      screen.queryByText(vendor.bank_account_reference),
    ).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole('button', {
        name: kind === 'executives' ? 'Añadir ejecutivo' : 'Añadir proveedor',
      }),
    );
    await userEvent.type(screen.getByLabelText('Nombre'), 'New context');
    if (kind === 'executives') {
      await userEvent.type(screen.getByLabelText('Cargo'), 'CEO');
      await userEvent.type(
        screen.getByLabelText('Correo legítimo'),
        'ceo@example.com',
      );
    } else {
      await userEvent.type(
        screen.getByLabelText('Dominio legítimo'),
        'new.example',
      );
    }
    await userEvent.click(
      screen.getByRole('button', { name: 'Guardar cambios' }),
    );
    await screen.findByText('Registro creado.');
    expect(
      fetch.mock.calls.some(
        ([url, init]) => url === '/api/' + kind && init?.method === 'POST',
      ),
    ).toBe(true);
    await userEvent.click(
      await screen.findByRole('button', {
        name:
          kind === 'executives'
            ? 'Editar ' + executive.name
            : 'Editar ' + vendor.name,
      }),
    );
    await userEvent.clear(screen.getByLabelText('Nombre'));
    await userEvent.type(screen.getByLabelText('Nombre'), 'Changed name');
    await userEvent.click(
      screen.getByRole('button', { name: 'Guardar cambios' }),
    );
    await screen.findByText('Cambios guardados.');
    await userEvent.click(
      await screen.findByRole('button', {
        name:
          kind === 'executives'
            ? 'Desactivar ' + executive.name
            : 'Desactivar ' + vendor.name,
      }),
    );
    await screen.findByText('Registro desactivado.');
    expect(
      fetch.mock.calls.some(
        ([, init]) =>
          init?.method === 'PATCH' &&
          String(init.body).includes('"is_active":false'),
      ),
    ).toBe(true);
  },
);
it.each(['ANALYST', 'AUDITOR'] as const)(
  'context is read only for %s',
  async (role) => {
    setup('/vendors', role);
    await screen.findByText(vendor.name);
    expect(
      screen.queryByRole('button', { name: 'Añadir proveedor' }),
    ).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole('button', { name: 'Ver ' + vendor.name }),
    );
    expect(screen.getByLabelText('Nombre')).toHaveAttribute('readonly');
    expect(
      screen.queryByRole('button', { name: 'Guardar cambios' }),
    ).not.toBeInTheDocument();
  },
);
it('manager can maintain executives', async () => {
  setup('/executives', 'MANAGER');
  await screen.findByRole('button', { name: 'Editar ' + executive.name });
  expect(
    screen.getByRole('button', { name: 'Añadir ejecutivo' }),
  ).toBeInTheDocument();
});
it('audit applies small server filters', async () => {
  const fetch = setup('/audit', 'AUDITOR');
  await screen.findByText('BEC_ALERT_CONFIRMED');
  await userEvent.type(screen.getByLabelText('Acción'), 'BEC_ALERT_CLAIMED');
  await userEvent.type(screen.getByLabelText('Recurso'), 'bec_alert');
  await userEvent.click(
    screen.getByRole('button', { name: 'Aplicar filtros' }),
  );
  await waitFor(() =>
    expect(
      fetch.mock.calls.some(
        ([url]) =>
          url.includes('action=BEC_ALERT_CLAIMED') &&
          url.includes('resource_type=bec_alert'),
      ),
    ).toBe(true),
  );
});
it('audit 403 preserves session and shows permission feedback', async () => {
  setup('/audit', 'ADMIN', { auditError: true });
  await screen.findByRole('alert');
  expect(screen.getByRole('alert')).toHaveTextContent('permisos');
  expect(sessionStorage.getItem(tokenKey)).toBe('t');
});
it('direct audit route is denied to analyst without API call', async () => {
  const fetch = setup('/audit', 'ANALYST');
  await screen.findByRole('alert');
  expect(fetch.mock.calls.some(([url]) => url.startsWith('/api/audit'))).toBe(
    false,
  );
});
it.each([
  ['/emails', 'Aún no hay correos recibidos.'],
  ['/executives', 'No hay ejecutivos registrados.'],
  ['/vendors', 'No hay proveedores registrados.'],
  ['/audit', 'No hay eventos con estos filtros.'],
])('empty state %s', async (path, text) => {
  setup(path, 'ADMIN', { empty: true });
  await screen.findByText(text);
});
