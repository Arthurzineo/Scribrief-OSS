import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

/** Page transitions must reach Django so it can recheck the session and object ACL. */
export function usePageNavigate() {
  const navigate = useNavigate();
  return (to, options) => {
    if (document.getElementById('root')?.dataset.mvt === '1') {
      if (options?.replace) window.location.replace(to);
      else window.location.assign(to);
      return;
    }
    navigate(to, options);
  };
}

export function PageRedirect({ to }) {
  const navigate = usePageNavigate();
  useEffect(() => { navigate(to, { replace: true }); }, [to]);
  return null;
}
