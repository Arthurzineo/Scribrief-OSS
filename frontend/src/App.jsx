import { useEffect } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from './shared/context/AuthContext.jsx';
import { MeetingsProvider } from './shared/context/MeetingsContext.jsx';
import Layout from './shared/Layout.jsx';
import LoginPage from './features/accounts/LoginPage.jsx';
import MeetingsPage from './features/meetings/MeetingsPage.jsx';
import NewMeetingPage from './features/meetings/NewMeetingPage.jsx';
import MeetingPage from './features/meetings/MeetingPage.jsx';
import AccountPage from './features/accounts/AccountPage.jsx';
import AdminPage from './features/admin/AdminPage.jsx';
import AdminLoginPage from './features/admin/AdminLoginPage.jsx';

const mvt = document.getElementById('root')?.dataset.mvt === '1';

function RequireAuth({ children }) {
  const { user, ready } = useAuth();
  const loc = useLocation();
  useEffect(() => {
    if (mvt && ready && !user) window.location.replace('/login/');
  }, [ready, user]);
  if (!ready) return null;
  if (!user) return mvt ? null : <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  return children;
}

export default function App() {
  if (mvt) return (
    <Routes>
      <Route path="/admin/login" element={<AdminLoginPage />} />
      <Route path="/admin" element={<AdminPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth><MeetingsProvider /></RequireAuth>}>
        <Route index element={<MeetingsPage />} />
        <Route path="reunioes/nova" element={<NewMeetingPage />} />
        <Route path="reunioes/:id" element={<MeetingPage tab="Transcrição" />} />
        <Route path="reunioes/:id/ata" element={<MeetingPage tab="Ata" />} />
        <Route path="reunioes/:id/mapa" element={<MeetingPage tab="Mapa mental" />} />
        <Route path="conta" element={<AccountPage />} />
      </Route>
    </Routes>
  );
  return (
    <Routes>
      <Route path="/admin/login" element={<AdminLoginPage />} />
      <Route path="/admin" element={<AdminPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={(
          <RequireAuth>
            <MeetingsProvider>
              <Layout />
            </MeetingsProvider>
          </RequireAuth>
        )}
      >
        <Route index element={<MeetingsPage />} />
        <Route path="reunioes/nova" element={<NewMeetingPage />} />
        <Route path="reunioes/:id" element={<MeetingPage tab="Transcrição" />} />
        <Route path="reunioes/:id/ata" element={<MeetingPage tab="Ata" />} />
        <Route path="reunioes/:id/mapa" element={<MeetingPage tab="Mapa mental" />} />
        <Route path="conta" element={<AccountPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
