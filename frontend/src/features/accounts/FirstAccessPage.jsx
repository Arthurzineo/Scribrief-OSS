import { PageRedirect } from '../../shared/lib/pageNavigation.js';
import { useAuth } from '../../shared/context/AuthContext.jsx';
import InitialPasswordPanel from './InitialPasswordPanel.jsx';

export default function FirstAccessPage() {
  const { user, ready } = useAuth();
  if (!ready) return null;
  if (!user) return <PageRedirect to="/login/" />;
  if (user.is_staff) return <PageRedirect to="/admin/" />;
  if (!user.must_change_password) return <PageRedirect to="/" />;
  return <InitialPasswordPanel />;
}
