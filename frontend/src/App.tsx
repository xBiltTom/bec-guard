import { useState } from 'react';
import type { FormEvent } from 'react';
import {
  BrowserRouter,
  Link,
  NavLink,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
} from 'react-router-dom';
import { ApiError, message } from './api';
import { AuthProvider, useAuth } from './auth';
import { ErrorState, LoadingState, PageHeader, label } from './components';

function Login() {
  const { user, login } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const location = useLocation();
  if (user)
    return (
      <Navigate
        to={(location.state as { from?: string } | null)?.from || '/'}
        replace
      />
    );
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const values = new FormData(form);
    setBusy(true);
    setError('');
    try {
      await login(String(values.get('email')), String(values.get('password')));
      form.reset();
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 401
          ? 'Correo o contraseña incorrectos.'
          : message(e),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login">
      <section className="login-intro">
        <Link className="brand" to="/login">
          <span className="brand-mark" aria-hidden="true">
            B
          </span>
          BEC Guard
        </Link>
        <h1>
          Una decisión informada.
          <br />
          Una amenaza contenida.
        </h1>
        <p>Revisa señales de fraude empresarial y documenta cada decisión.</p>
        <div className="login-rule">Detección explicable. Revisión humana.</div>
      </section>
      <section className="login-form">
        <form onSubmit={(e) => void submit(e)}>
          <h2>Iniciar sesión</h2>
          <p>Accede a tu espacio de revisión.</p>
          <label htmlFor="email">Correo electrónico</label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="username"
            required
            maxLength={320}
          />
          <label htmlFor="password">Contraseña</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            maxLength={128}
          />
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <button disabled={busy} type="submit">
            {busy ? 'Iniciando sesión…' : 'Iniciar sesión'}
          </button>
        </form>
      </section>
    </main>
  );
}
function Protected() {
  const { user, loading, error, retry } = useAuth();
  const location = useLocation();
  if (loading) return <LoadingState />;
  if (error) return <ErrorState error={error} retry={retry} />;
  return user ? (
    <Outlet />
  ) : (
    <Navigate to="/login" state={{ from: location.pathname }} replace />
  );
}
function Shell() {
  const { user, logout } = useAuth();
  const [menu, setMenu] = useState(false);
  const items = [
    ['/', 'Dashboard'],
    ['/alerts', 'Alertas'],
    ['/emails', 'Correos'],
    ['/executives', 'Ejecutivos'],
    ['/vendors', 'Proveedores'],
  ];
  if (user?.role === 'ADMIN' || user?.role === 'AUDITOR')
    items.push(['/audit', 'Auditoría']);
  return (
    <div className="app">
      <a className="skip" href="#content">
        Saltar al contenido
      </a>
      <aside className={menu ? 'sidebar expanded' : 'sidebar'}>
        <Link className="brand" to="/">
          <span className="brand-mark" aria-hidden="true">
            B
          </span>
          BEC Guard
        </Link>
        <button
          className="menu-toggle secondary"
          aria-expanded={menu}
          aria-controls="main-nav"
          onClick={() => setMenu(!menu)}
        >
          Menú
        </button>
        <nav id="main-nav" aria-label="Navegación principal">
          {items.map(([path, title]) => (
            <NavLink
              key={path}
              to={path}
              end={path === '/'}
              onClick={() => setMenu(false)}
            >
              {title}
            </NavLink>
          ))}
        </nav>
        <p className="sidebar-note">
          Prevención de fraude
          <br />
          Revisión y trazabilidad
        </p>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span>Centro de revisión</span>
          <div>
            <span className="identity">
              {user?.name}
              <small>{label(user?.role)}</small>
            </span>
            <button className="secondary" onClick={logout}>
              Cerrar sesión
            </button>
          </div>
        </header>
        <main id="content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
function Foundation() {
  return (
    <PageHeader
      title="Centro de revisión"
      description="Consulta la evidencia y registra tus decisiones."
    />
  );
}
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Protected />}>
        <Route element={<Shell />}>
          <Route index element={<Foundation />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
