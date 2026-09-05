import { Link } from 'react-router-dom'

import { useInfo } from '../hooks/useInfo'

export function HomePage() {
  const { data, isPending, isError, error } = useInfo()

  return (
    <main>
      <h1>LivePhoto</h1>
      <p>Secure passive liveness platform</p>
      <p>Foundation environment ready.</p>
      <p>
        <Link to="/capture">Go to camera capture</Link>
      </p>

      {isPending && <p role="status">Loading application info…</p>}
      {isError && (
        <p role="alert">
          Unable to load application info
          {error instanceof Error && error.message ? `: ${error.message}` : ''}
        </p>
      )}
      {data && (
        <dl>
          <div>
            <dt>Name</dt>
            <dd>{data.name}</dd>
          </div>
          <div>
            <dt>Version</dt>
            <dd>{data.version}</dd>
          </div>
          <div>
            <dt>Environment</dt>
            <dd>{data.environment}</dd>
          </div>
        </dl>
      )}
    </main>
  )
}
