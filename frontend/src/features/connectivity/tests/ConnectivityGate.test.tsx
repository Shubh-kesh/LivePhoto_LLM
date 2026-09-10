/**
 * ConnectivityGate tests (pre-M6 connectivity/browser/policy preflight).
 *
 * A "capable environment" mirrors a modern browser (secure context, mediaDevices, canvas toBlob,
 * object URLs, supported user agent). Individual tests remove one capability / downgrade the
 * browser / change the server policy to prove the gate fails safe.
 * `apiRequest` (the backend reachability + policy probe) is mocked; camera permission is never
 * requested by the gate itself.
 */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { StrictMode, useEffect, useState } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  installCanvasFakes,
  installMediaDevices,
  installObjectUrlFakes,
  removeMediaDevices,
  setSecureContext,
} from '../../capture/tests/mediaFakes'
import App from '../../../app/App'
import { ConnectivityGate } from '../ConnectivityGate'

vi.mock('../../../api/client', () => ({
  apiRequest: vi.fn(),
}))

import { apiRequest } from '../../../api/client'

const mockedApiRequest = vi.mocked(apiRequest)

vi.mock('../../capture/CapturePage', () => ({
  CapturePage: () => <div data-testid="capture-page">capture</div>,
}))

vi.mock('../../integration/api', () => ({
  fetchBrowserSession: vi.fn(),
  registerAttempt: vi.fn(),
  uploadCapture: vi.fn(),
  browserLiveness: vi.fn(),
  triggerPortrait: vi.fn(),
  submitForConsumer: vi.fn(),
  allowlistedAttemptReason: (codes: readonly string[]) => codes[0],
}))

import { fetchBrowserSession } from '../../integration/api'

const mockedFetchBrowserSession = vi.mocked(fetchBrowserSession)

const POLICY = {
  policy_version: 'browser-policy-v1',
  browsers: {
    chrome: { minimum_major: 120, enabled: true },
    edge: { minimum_major: 120, enabled: true },
    firefox: { minimum_major: 120, enabled: true },
    safari: { minimum_major: 17, enabled: true },
    ios_safari: { minimum_major: 17, enabled: true },
    android_chrome: { minimum_major: 120, enabled: true },
  },
}

const INFO = { name: 'LivePhoto', version: '1.0', environment: 'test', browser_policy: POLICY }

const SUPPORTED_CHROME_UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'

function setOnLine(value: boolean): void {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value })
}

function setUserAgent(ua: string): void {
  Object.defineProperty(navigator, 'userAgent', { configurable: true, get: () => ua })
}

/** Install the API surface a modern browser provides; returns the mediaDevices handles. */
function installCapableEnvironment() {
  setSecureContext(true)
  setOnLine(true)
  setUserAgent(SUPPORTED_CHROME_UA)
  const mediaDevices = installMediaDevices()
  installCanvasFakes()
  installObjectUrlFakes()
  return mediaDevices
}

function ProbeJourney({ label = 'journey' }: { label?: string }) {
  return <div data-testid={`probe-${label}`}>journey</div>
}

function MountCounter() {
  const [count, setCount] = useState(0)
  useEffect(() => setCount((c) => c + 1), [])
  return <div data-testid="mount-count">{count}</div>
}

function deferred<T = unknown>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('ConnectivityGate', () => {
  beforeEach(() => {
    mockedApiRequest.mockReset()
    mockedFetchBrowserSession.mockReset()
  })

  it('startup offline shows offline UI, never probes the backend, never requests camera', async () => {
    const env = installCapableEnvironment()
    setOnLine(false)
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    expect(await screen.findByText('No internet connection')).toBeInTheDocument()
    expect(screen.getByText('Connect to the internet to continue.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    expect(screen.queryByTestId('probe-journey')).not.toBeInTheDocument()
    expect(mockedApiRequest).not.toHaveBeenCalled()
    expect(env.getUserMedia).not.toHaveBeenCalled()
  })

  it('online + reachable backend proceeds to the journey without requesting camera', async () => {
    const env = installCapableEnvironment()
    mockedApiRequest.mockResolvedValue(INFO)
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    expect(await screen.findByTestId('probe-journey')).toBeInTheDocument()
    expect(env.getUserMedia).not.toHaveBeenCalled()
  })

  it('online but backend unreachable shows backend-unreachable UI and does not request camera', async () => {
    const env = installCapableEnvironment()
    mockedApiRequest.mockRejectedValue(new Error('network down'))
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    expect(await screen.findByText("We can't connect right now.")).toBeInTheDocument()
    expect(screen.getByText('Check your internet connection and try again.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    expect(screen.queryByTestId('probe-journey')).not.toBeInTheDocument()
    expect(env.getUserMedia).not.toHaveBeenCalled()
  })

  it('Try again re-probes and resumes the journey once the backend is reachable', async () => {
    installCapableEnvironment()
    mockedApiRequest.mockRejectedValueOnce(new Error('down')).mockResolvedValue(INFO)
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    await screen.findByText("We can't connect right now.")
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByTestId('probe-journey')).toBeInTheDocument()
    expect(mockedApiRequest).toHaveBeenCalledTimes(2)
  })

  it('offline -> online event re-runs the real backend probe and does not resume until it succeeds', async () => {
    const env = installCapableEnvironment()
    mockedApiRequest.mockResolvedValue(INFO)
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    await screen.findByTestId('probe-journey')

    // Browser reports the connection dropped while the app is loaded.
    setOnLine(false)
    act(() => {
      window.dispatchEvent(new Event('offline'))
    })
    expect(await screen.findByText('No internet connection')).toBeInTheDocument()
    expect(screen.getByTestId('probe-journey')).toBeInTheDocument()

    // The browser fires `online` but the backend is still down: a real probe runs and the journey
    // must NOT resume.
    setOnLine(true)
    mockedApiRequest.mockRejectedValue(new Error('still down'))
    act(() => {
      window.dispatchEvent(new Event('online'))
    })
    expect(await screen.findByText("We can't connect right now.")).toBeInTheDocument()
    expect(screen.getByTestId('probe-journey')).toBeInTheDocument()
    expect(mockedApiRequest).toHaveBeenCalledTimes(2)

    // Only a successful probe resumes the journey.
    mockedApiRequest.mockResolvedValue(INFO)
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByTestId('probe-journey')).toBeInTheDocument()
    expect(env.getUserMedia).not.toHaveBeenCalled()
  })

  it('offline event while loaded shows a safe overlay and preserves mounted children', async () => {
    installCapableEnvironment()
    mockedApiRequest.mockResolvedValue(INFO)
    render(
      <ConnectivityGate>
        <MountCounter />
      </ConnectivityGate>,
    )
    await screen.findByTestId('mount-count')
    await waitFor(() => expect(screen.getByTestId('mount-count').textContent).toBe('1'))

    setOnLine(false)
    act(() => {
      window.dispatchEvent(new Event('offline'))
    })
    expect(await screen.findByText('No internet connection')).toBeInTheDocument()
    // Children stay mounted (no remount => the mount effect does not re-run).
    expect(screen.getByTestId('mount-count').textContent).toBe('1')
  })

  it('getUserMedia unavailable shows browser-not-supported UI and never probes the backend', async () => {
    installCapableEnvironment()
    removeMediaDevices()
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    expect(await screen.findByText('Browser not supported')).toBeInTheDocument()
    expect(
      screen.getByText('Please use an updated version of Chrome, Edge, Firefox, or Safari.'),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('probe-journey')).not.toBeInTheDocument()
    expect(mockedApiRequest).not.toHaveBeenCalled()
  })

  it('insecure context shows the preserved secure-context message', async () => {
    installCapableEnvironment()
    setSecureContext(false)
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    expect(await screen.findByText('Camera requires a secure connection')).toBeInTheDocument()
    expect(screen.getByText('Use HTTPS to open LivePhoto.')).toBeInTheDocument()
    expect(screen.queryByTestId('probe-journey')).not.toBeInTheDocument()
  })

  it('mounting the gate never requests camera permission', async () => {
    const env = installCapableEnvironment()
    mockedApiRequest.mockResolvedValue(INFO)
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    await screen.findByTestId('probe-journey')
    expect(env.getUserMedia).not.toHaveBeenCalled()
  })

  it('StrictMode double-effects do not duplicate reachability probes', async () => {
    installCapableEnvironment()
    mockedApiRequest.mockResolvedValue(INFO)
    render(
      <StrictMode>
        <ConnectivityGate>
          <ProbeJourney />
        </ConnectivityGate>
      </StrictMode>,
    )
    expect(await screen.findByTestId('probe-journey')).toBeInTheDocument()
    expect(mockedApiRequest).toHaveBeenCalledTimes(1)
  })

  it('re-renders after readiness do not re-run the reachability probe', async () => {
    installCapableEnvironment()
    mockedApiRequest.mockResolvedValue(INFO)
    const { rerender } = render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    await screen.findByTestId('probe-journey')
    rerender(
      <ConnectivityGate>
        <ProbeJourney />
        <span data-testid="extra">extra</span>
      </ConnectivityGate>,
    )
    expect(screen.getByTestId('extra')).toBeInTheDocument()
    expect(mockedApiRequest).toHaveBeenCalledTimes(1)
  })

  it('A: a stale probe success never overwrites an OFFLINE event', async () => {
    installCapableEnvironment()
    setOnLine(true)
    const first = deferred()
    mockedApiRequest.mockReturnValue(first.promise)
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    await waitFor(() => expect(mockedApiRequest).toHaveBeenCalledTimes(1))

    // Browser reports offline while the probe is still in flight.
    setOnLine(false)
    act(() => {
      window.dispatchEvent(new Event('offline'))
    })
    await screen.findByText('No internet connection')

    // The OLD probe completes success late: it must be discarded, never READY.
    await act(async () => {
      first.resolve(INFO)
    })
    expect(screen.getByRole('heading', { name: 'No internet connection' })).toBeInTheDocument()
    expect(screen.queryByTestId('probe-journey')).not.toBeInTheDocument()
  })

  it('B: online while a probe is in flight queues a fresh probe; READY only after it succeeds', async () => {
    installCapableEnvironment()
    setOnLine(true)
    const first = deferred()
    const second = deferred()
    mockedApiRequest.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    await waitFor(() => expect(mockedApiRequest).toHaveBeenCalledTimes(1))

    // Offline invalidates the first probe; online arrives while it is still in flight.
    setOnLine(false)
    act(() => {
      window.dispatchEvent(new Event('offline'))
    })
    await screen.findByText('No internet connection')
    setOnLine(true)
    act(() => {
      window.dispatchEvent(new Event('online'))
    })

    // The old (now stale) probe fails: it must not leave the gate stuck, and a fresh probe must
    // run automatically.
    await act(async () => {
      first.reject(new Error('down'))
    })
    await waitFor(() => expect(mockedApiRequest).toHaveBeenCalledTimes(2))

    // READY only after the NEW probe succeeds.
    await act(async () => {
      second.resolve(INFO)
    })
    await screen.findByTestId('probe-journey')
  })

  it('C: an old probe success cannot overwrite a newer failed check', async () => {
    installCapableEnvironment()
    setOnLine(true)
    const first = deferred()
    const second = deferred()
    mockedApiRequest.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    await waitFor(() => expect(mockedApiRequest).toHaveBeenCalledTimes(1))

    // Offline then online while the first probe is in flight -> a fresh probe is queued.
    setOnLine(false)
    act(() => {
      window.dispatchEvent(new Event('offline'))
    })
    await screen.findByText('No internet connection')
    setOnLine(true)
    act(() => {
      window.dispatchEvent(new Event('online'))
    })

    // The old probe reports success late: it must be discarded (never READY).
    await act(async () => {
      first.resolve(INFO)
    })
    expect(screen.queryByTestId('probe-journey')).not.toBeInTheDocument()

    // The newer probe fails: the newer (failed) check wins, backend-unreachable UI.
    await waitFor(() => expect(mockedApiRequest).toHaveBeenCalledTimes(2))
    await act(async () => {
      second.reject(new Error('still down'))
    })
    await screen.findByText("We can't connect right now.")
    expect(screen.queryByTestId('probe-journey')).not.toBeInTheDocument()
  })

  it('D: rapid online events while one probe is active never create parallel probes', async () => {
    installCapableEnvironment()
    setOnLine(true)
    const first = deferred()
    const second = deferred()
    mockedApiRequest.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    await waitFor(() => expect(mockedApiRequest).toHaveBeenCalledTimes(1))

    // Three online events while the first probe is in flight.
    act(() => {
      window.dispatchEvent(new Event('online'))
    })
    act(() => {
      window.dispatchEvent(new Event('online'))
    })
    act(() => {
      window.dispatchEvent(new Event('online'))
    })
    // Still exactly one probe in flight (no parallel probes).
    expect(mockedApiRequest).toHaveBeenCalledTimes(1)

    // The queued rechecks collapse into a single fresh probe, not one per event.
    await act(async () => {
      first.resolve(INFO)
    })
    await waitFor(() => expect(mockedApiRequest).toHaveBeenCalledTimes(2))
    await act(async () => {
      second.resolve(INFO)
    })
    await screen.findByTestId('probe-journey')
  })

  it('E: the reachability probe explicitly uses cache: no-store', async () => {
    installCapableEnvironment()
    mockedApiRequest.mockResolvedValue(INFO)
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    await screen.findByTestId('probe-journey')
    expect(mockedApiRequest).toHaveBeenCalledWith(
      '/api/v1/info',
      expect.objectContaining({ cache: 'no-store' }),
    )
  })

  it('policy 1: reachable backend + supported browser + version >= minimum + capabilities -> journey mounts', async () => {
    const env = installCapableEnvironment()
    setUserAgent(SUPPORTED_CHROME_UA)
    mockedApiRequest.mockResolvedValue(INFO)
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    expect(await screen.findByTestId('probe-journey')).toBeInTheDocument()
    expect(env.getUserMedia).not.toHaveBeenCalled()
  })

  it('policy 2: browser below minimum -> Browser update required, no journey, no camera', async () => {
    const env = installCapableEnvironment()
    setUserAgent(
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36',
    )
    mockedApiRequest.mockResolvedValue(INFO)
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    expect(
      await screen.findByRole('heading', { name: 'Browser update required' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        'Your browser version is no longer supported. Please update your browser to continue.',
      ),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('probe-journey')).not.toBeInTheDocument()
    expect(env.getUserMedia).not.toHaveBeenCalled()
    // No "Continue anyway" option.
    expect(screen.queryByRole('button', { name: /continue anyway/i })).not.toBeInTheDocument()
  })

  it('policy 3: browser exactly at minimum -> allowed', async () => {
    installCapableEnvironment()
    setUserAgent(
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    )
    mockedApiRequest.mockResolvedValue(INFO)
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    expect(await screen.findByTestId('probe-journey')).toBeInTheDocument()
  })

  it('policy 4: unknown browser family -> Browser not supported', async () => {
    const env = installCapableEnvironment()
    setUserAgent('Mozilla/5.0 (compatible; LegacyBrowser/1.0)')
    mockedApiRequest.mockResolvedValue(INFO)
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    expect(
      await screen.findByRole('heading', { name: 'Browser not supported' }),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('probe-journey')).not.toBeInTheDocument()
    expect(env.getUserMedia).not.toHaveBeenCalled()
  })

  it('policy 5: recognized browser with unparseable version -> safe blocking state', async () => {
    installCapableEnvironment()
    setUserAgent(
      'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/ Safari/537.36',
    )
    mockedApiRequest.mockResolvedValue(INFO)
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    expect(
      await screen.findByRole('heading', { name: 'Browser update required' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        "We couldn't verify that this browser version is supported. Please update your browser or use a supported browser.",
      ),
    ).toBeInTheDocument()
    // The raw user-agent string is never shown to customers.
    expect(screen.queryByText(/Mozilla\/5\.0 \(X11/)).not.toBeInTheDocument()
  })

  it('policy 6: Check again fetches a fresh /info, re-evaluates, and proceeds when the policy allows', async () => {
    installCapableEnvironment()
    setUserAgent(SUPPORTED_CHROME_UA)
    const blockingPolicy = {
      ...POLICY,
      browsers: { ...POLICY.browsers, chrome: { minimum_major: 999, enabled: true } },
    }
    mockedApiRequest
      .mockResolvedValueOnce({ ...INFO, browser_policy: blockingPolicy })
      .mockResolvedValueOnce(INFO)
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    expect(
      await screen.findByRole('heading', { name: 'Browser update required' }),
    ).toBeInTheDocument()

    // Check again -> fresh /info (no-store) -> policy now allows -> journey proceeds.
    fireEvent.click(screen.getByRole('button', { name: 'Check again' }))
    expect(await screen.findByTestId('probe-journey')).toBeInTheDocument()
    expect(mockedApiRequest).toHaveBeenCalledTimes(2)
    expect(mockedApiRequest).toHaveBeenLastCalledWith(
      '/api/v1/info',
      expect.objectContaining({ cache: 'no-store' }),
    )
  })

  it('policy 7: offline remains offline regardless of browser policy', async () => {
    installCapableEnvironment()
    setUserAgent(
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36',
    )
    setOnLine(false)
    mockedApiRequest.mockResolvedValue(INFO)
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    expect(
      await screen.findByRole('heading', { name: 'No internet connection' }),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('probe-journey')).not.toBeInTheDocument()
    expect(mockedApiRequest).not.toHaveBeenCalled()
  })

  it('policy 8: backend unreachable remains backend-unreachable regardless of browser', async () => {
    const env = installCapableEnvironment()
    setUserAgent(SUPPORTED_CHROME_UA)
    mockedApiRequest.mockRejectedValue(new Error('network down'))
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    expect(await screen.findByText("We can't connect right now.")).toBeInTheDocument()
    expect(screen.queryByTestId('probe-journey')).not.toBeInTheDocument()
    expect(env.getUserMedia).not.toHaveBeenCalled()
  })

  it('policy 9: a stale connectivity probe cannot move the gate to READY', async () => {
    installCapableEnvironment()
    setUserAgent(SUPPORTED_CHROME_UA)
    setOnLine(true)
    const first = deferred()
    mockedApiRequest.mockReturnValue(first.promise)
    render(
      <ConnectivityGate>
        <ProbeJourney />
      </ConnectivityGate>,
    )
    await waitFor(() => expect(mockedApiRequest).toHaveBeenCalledTimes(1))
    setOnLine(false)
    act(() => {
      window.dispatchEvent(new Event('offline'))
    })
    await screen.findByText('No internet connection')
    // Old probe succeeds late (INFO now carries the policy too): still must NOT become READY.
    await act(async () => {
      first.resolve(INFO)
    })
    expect(screen.queryByTestId('probe-journey')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'No internet connection' })).toBeInTheDocument()
  })

  it('policy 10: StrictMode does not generate duplicate probe storms', async () => {
    installCapableEnvironment()
    setUserAgent(SUPPORTED_CHROME_UA)
    mockedApiRequest.mockResolvedValue(INFO)
    render(
      <StrictMode>
        <ConnectivityGate>
          <ProbeJourney />
        </ConnectivityGate>
      </StrictMode>,
    )
    expect(await screen.findByTestId('probe-journey')).toBeInTheDocument()
    expect(mockedApiRequest).toHaveBeenCalledTimes(1)
  })
})

describe('App wiring with the connectivity gate', () => {
  beforeEach(() => {
    mockedApiRequest.mockReset()
    mockedFetchBrowserSession.mockReset()
    installCapableEnvironment()
    mockedApiRequest.mockResolvedValue(INFO)
  })

  it('/capture proceeds after a successful preflight', async () => {
    render(
      <MemoryRouter initialEntries={['/capture']}>
        <App />
      </MemoryRouter>,
    )
    expect(await screen.findByTestId('capture-page')).toBeInTheDocument()
  })

  it('/xbiz/live_photo proceeds after a successful preflight with an active session', async () => {
    mockedFetchBrowserSession.mockResolvedValue({
      state: 'active',
      submission_ready: false,
      attempt_count: 0,
      max_attempts: 10,
      reason_codes: [],
    })
    render(
      <MemoryRouter initialEntries={['/xbiz/live_photo']}>
        <App />
      </MemoryRouter>,
    )
    expect(await screen.findByTestId('capture-page')).toBeInTheDocument()
  })

  it('invalid/expired xbiz session stays a session error, not a connectivity error', async () => {
    mockedFetchBrowserSession.mockResolvedValue({
      state: 'invalid',
      submission_ready: false,
    })
    render(
      <MemoryRouter initialEntries={['/xbiz/live_photo']}>
        <App />
      </MemoryRouter>,
    )
    expect(await screen.findByText('Link unavailable')).toBeInTheDocument()
    expect(screen.queryByText("We can't connect right now.")).not.toBeInTheDocument()
    expect(screen.queryByText('No internet connection')).not.toBeInTheDocument()
  })
})
