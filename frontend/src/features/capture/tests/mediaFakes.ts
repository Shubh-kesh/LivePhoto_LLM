/**
 * Reusable fake media layer for M2 tests (M2 §71). No real camera is required.
 *
 * - MediaDevices / MediaStream / MediaStreamTrack fakes
 * - HTMLVideoElement behavior (dimensions, play, requestVideoFrameCallback)
 * - canvas/blob encoding fakes
 * - object-URL pairing fakes
 *
 * Kept in one place so M3 can reuse the same fakes.
 */

import { vi } from 'vitest'
import type { Mock } from 'vitest'

import type { VideoFrameCallbackMetadata } from '../types/camera'

// ---------------------------------------------------------------------------
// Secure context / mediaDevices
// ---------------------------------------------------------------------------

export function setSecureContext(value: boolean): void {
  Object.defineProperty(window, 'isSecureContext', { configurable: true, value })
}

export interface FakeTrackExtras {
  stopCount: () => number
  emitEnded: () => void
  readyStateValue: () => MediaStreamTrackState
}

export interface FakeTrackOptions {
  facingMode?: string
  width?: number
  height?: number
  frameRate?: number
  deviceId?: string
}

export function createFakeTrack(options: FakeTrackOptions = {}) {
  const listeners = new Map<string, Set<EventListener>>()
  let readyState: MediaStreamTrackState = 'live'
  let stopCalls = 0

  const emit = (type: string) => {
    const set = listeners.get(type)
    if (!set) return
    const event = { type } as Event
    for (const listener of set) {
      listener(event)
    }
  }

  const track = {
    kind: 'video',
    label: 'Fake camera',
    readyState,
    enabled: true,
    muted: false,
    getSettings: vi.fn(() => ({
      facingMode: options.facingMode ?? 'user',
      width: options.width ?? 640,
      height: options.height ?? 480,
      frameRate: options.frameRate ?? 30,
      aspectRatio: (options.width ?? 640) / (options.height ?? 480),
      deviceId: options.deviceId ?? 'fake-device-1',
      groupId: 'fake-group-1',
    })),
    getCapabilities: vi.fn(() => ({})),
    stop: vi.fn(() => {
      stopCalls += 1
      readyState = 'ended'
      emit('ended')
    }),
    addEventListener: vi.fn((type: string, listener: EventListener) => {
      const set = listeners.get(type) ?? new Set<EventListener>()
      set.add(listener)
      listeners.set(type, set)
    }),
    removeEventListener: vi.fn((type: string, listener: EventListener) => {
      listeners.get(type)?.delete(listener)
    }),
    dispatchEvent: vi.fn((event: Event) => {
      emit(event.type)
      return true
    }),
  } as unknown as MediaStreamTrack & FakeTrackExtras

  const extras: FakeTrackExtras = {
    stopCount: () => stopCalls,
    emitEnded: () => emit('ended'),
    readyStateValue: () => readyState,
  }
  return Object.assign(track, extras)
}

export interface FakeStreamExtras {
  track: ReturnType<typeof createFakeTrack>
}

export function createFakeStream(options: FakeTrackOptions = {}) {
  const track = createFakeTrack(options)
  const stream = {
    getVideoTracks: vi.fn(() => [track]),
    getTracks: vi.fn(() => [track]),
    getAudioTracks: vi.fn(() => []),
    stop: vi.fn(() => {
      track.stop()
    }),
  } as unknown as MediaStream
  return { stream, track } as { stream: MediaStream } & FakeStreamExtras & { track: typeof track }
}

export function createDeviceInfo(
  kind: MediaDeviceKind,
  deviceId: string,
  label = 'Fake ' + kind,
): MediaDeviceInfo {
  return { kind, label, deviceId, groupId: 'fake-group-1', toJSON: () => ({}) } as MediaDeviceInfo
}

export interface MediaDevicesHandles {
  getUserMedia: Mock<(constraints: MediaStreamConstraints) => Promise<MediaStream>>
  enumerateDevices: Mock<() => Promise<MediaDeviceInfo[]>>
}

export function installMediaDevices(): MediaDevicesHandles {
  const getUserMedia = vi.fn(() => Promise.resolve(createFakeStream().stream))
  const enumerateDevices = vi.fn(() =>
    Promise.resolve([createDeviceInfo('videoinput', 'fake-cam-1')]),
  )
  const mediaDevices = { getUserMedia, enumerateDevices }
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: mediaDevices })
  return { getUserMedia, enumerateDevices }
}

export function removeMediaDevices(): void {
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: undefined })
}

// ---------------------------------------------------------------------------
// Video element behavior
// ---------------------------------------------------------------------------

export interface VideoDriver {
  width: number
  height: number
  play: Mock
  pause: Mock
  useRvf: boolean
}

export function installVideoBehavior(options: { useRvf?: boolean } = {}) {
  const driver: VideoDriver = {
    width: 640,
    height: 480,
    play: vi.fn().mockResolvedValue(undefined),
    pause: vi.fn(),
    useRvf: options.useRvf ?? true,
  }

  Object.defineProperty(HTMLVideoElement.prototype, 'videoWidth', {
    configurable: true,
    get: () => driver.width,
  })
  Object.defineProperty(HTMLVideoElement.prototype, 'videoHeight', {
    configurable: true,
    get: () => driver.height,
  })
  HTMLVideoElement.prototype.play = driver.play as unknown as typeof HTMLVideoElement.prototype.play
  HTMLVideoElement.prototype.pause =
    driver.pause as unknown as typeof HTMLVideoElement.prototype.pause

  if (driver.useRvf) {
    installRvfOnPrototype()
  } else {
    delete (HTMLVideoElement.prototype as Partial<HTMLVideoElement>).requestVideoFrameCallback
    installRafGlobally()
  }

  return driver
}

/** requestVideoFrameCallback fake: each registered callback fires once with increasing timestamps. */
function installRvfOnPrototype(): void {
  let pending: ((now: number, meta: VideoFrameCallbackMetadata) => void) | null = null
  let index = 0
  let timer: ReturnType<typeof setTimeout> | null = null

  const schedule = () => {
    if (timer !== null) return
    timer = setTimeout(() => {
      timer = null
      if (pending) {
        const callback = pending
        pending = null
        index += 1
        callback(index * 150, {
          presentationTime: index * 150,
          expectedDisplayTime: index * 150,
          width: 640,
          height: 480,
          mediaTime: index * 0.04,
          presentedFrames: index,
        })
      }
    }, 0)
  }

  ;(HTMLVideoElement.prototype as unknown as Record<string, unknown>).requestVideoFrameCallback =
    vi.fn((callback: (now: number, meta: VideoFrameCallbackMetadata) => void) => {
      pending = callback
      schedule()
      return index
    })
  ;(HTMLVideoElement.prototype as unknown as Record<string, unknown>).cancelVideoFrameCallback =
    vi.fn()
}

/** requestAnimationFrame fake: each registered callback fires once with increasing timestamps. */
export function installRafGlobally(): void {
  let pending: FrameRequestCallback | null = null
  let index = 0
  let timer: ReturnType<typeof setTimeout> | null = null

  const schedule = () => {
    if (timer !== null) return
    timer = setTimeout(() => {
      timer = null
      if (pending) {
        const callback = pending
        pending = null
        index += 1
        callback(index * 150)
      }
    }, 0)
  }

  globalThis.requestAnimationFrame = ((callback: FrameRequestCallback) => {
    pending = callback
    schedule()
    return index
  }) as typeof requestAnimationFrame
}

export function removeRafGlobally(): void {
  // @ts-expect-error -- restoring the unset jsdom default
  delete globalThis.requestAnimationFrame
}

// ---------------------------------------------------------------------------
// Canvas / blob encoding
// ---------------------------------------------------------------------------

export interface CanvasHandles {
  drawImage: Mock
  getContext: Mock
  toBlob: Mock
  setGetContextNull: (value: boolean) => void
  setToBlob: (fn: (callIndex: number) => Blob | null) => void
  callCount: () => number
}

export function installCanvasFakes(): CanvasHandles {
  const drawImage = vi.fn()
  const getContext = vi.fn()
  const toBlob = vi.fn()
  let nullContext = false
  let toBlobImpl: ((callIndex: number) => Blob | null) | null = null
  let calls = 0

  HTMLCanvasElement.prototype.getContext =
    getContext as unknown as typeof HTMLCanvasElement.prototype.getContext
  HTMLCanvasElement.prototype.toBlob =
    toBlob as unknown as typeof HTMLCanvasElement.prototype.toBlob

  getContext.mockImplementation(function getContextImpl(this: HTMLCanvasElement) {
    if (nullContext) return null
    return {
      drawImage,
      canvas: this,
    }
  })

  toBlob.mockImplementation(function toBlobImpl(
    this: HTMLCanvasElement,
    callback: BlobCallback,
    _mimeType?: string,
    _quality?: number,
  ) {
    calls += 1
    window.setTimeout(() => {
      const blob = toBlobImplFn(calls)
      callback(blob)
    }, 0)
  })

  const toBlobImplFn = (callIndex: number): Blob | null => {
    if (toBlobImpl) return toBlobImpl(callIndex)
    return new Blob([new Uint8Array([1, 2, 3])], { type: 'image/jpeg' })
  }

  return {
    drawImage,
    getContext,
    toBlob,
    setGetContextNull: (value: boolean) => {
      nullContext = value
    },
    setToBlob: (fn: (callIndex: number) => Blob | null) => {
      toBlobImpl = fn
    },
    callCount: () => calls,
  }
}

// ---------------------------------------------------------------------------
// Object URLs
// ---------------------------------------------------------------------------

export interface ObjectUrlHandles {
  createObjectURL: Mock<(blob: Blob) => string>
  revokeObjectURL: Mock<(url: string) => void>
}

export function installObjectUrlFakes(): ObjectUrlHandles {
  let counter = 0
  const createObjectURL = vi.fn((_blob: Blob) => `blob:fake-${(counter += 1)}`)
  const revokeObjectURL = vi.fn()
  URL.createObjectURL = createObjectURL as unknown as typeof URL.createObjectURL
  URL.revokeObjectURL = revokeObjectURL as unknown as typeof URL.revokeObjectURL
  return { createObjectURL, revokeObjectURL }
}

// ---------------------------------------------------------------------------
// All-in-one environment
// ---------------------------------------------------------------------------

export interface MediaEnvironment {
  mediaDevices: MediaDevicesHandles
  objectUrls: ObjectUrlHandles
  canvas: CanvasHandles
  video: VideoDriver
}

export function setupMediaEnvironment(options: { useRvf?: boolean } = {}): MediaEnvironment {
  setSecureContext(true)
  const mediaDevices = installMediaDevices()
  const objectUrls = installObjectUrlFakes()
  const canvas = installCanvasFakes()
  const video = installVideoBehavior({ useRvf: options.useRvf ?? true })
  return { mediaDevices, objectUrls, canvas, video }
}
