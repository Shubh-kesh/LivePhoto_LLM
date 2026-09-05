/**
 * Media-layer unit tests (M2 §36-39, §19, §27, §34): error mapping, availability detection,
 * safe settings, burst scheduling and bundle/representative selection. Uses plain elements with
 * the fake media layer installed.
 */

import { describe, expect, it } from 'vitest'

import { extractSafeSettings, requestCameraStream } from '../media/camera'
import {
  captureBurst,
  isVideoReady,
  supportsRequestVideoFrameCallback,
} from '../media/frameCapture'
import { createCaptureBundle } from '../media/bundle'
import {
  CameraError,
  checkCameraAvailability,
  toCameraError,
  type CameraErrorCode,
} from '../media/mediaErrors'
import { selectRepresentativeFrame } from '../utils/representative'
import type { CaptureFrame } from '../types/capture'
import {
  createFakeStream,
  removeMediaDevices,
  setSecureContext,
  setupMediaEnvironment,
} from './mediaFakes'

describe('camera error mapping', () => {
  it('maps each relevant DOMException name to a stable code', () => {
    const cases: Array<[string, CameraErrorCode]> = [
      ['NotAllowedError', 'CAMERA_PERMISSION_DENIED'],
      ['NotFoundError', 'CAMERA_NOT_FOUND'],
      ['NotReadableError', 'CAMERA_IN_USE_OR_UNREADABLE'],
      ['OverconstrainedError', 'CAMERA_CONSTRAINT_FAILED'],
      ['AbortError', 'CAMERA_START_FAILED'],
      ['SecurityError', 'INSECURE_CONTEXT'],
      ['InvalidStateError', 'CAMERA_INTERRUPTED'],
      ['TypeError', 'CAMERA_CONSTRAINT_FAILED'],
    ]
    for (const [name, code] of cases) {
      expect(toCameraError(new DOMException('boom', name)).code).toBe(code)
    }
  })

  it('passes CameraError instances through unchanged', () => {
    const original = new CameraError('CAMERA_INTERRUPTED')
    const mapped = toCameraError(original)
    expect(mapped).toBe(original)
    expect(mapped.code).toBe('CAMERA_INTERRUPTED')
  })

  it('maps unknown errors to UNKNOWN_CAMERA_ERROR', () => {
    expect(toCameraError(new Error('weird')).code).toBe('UNKNOWN_CAMERA_ERROR')
  })

  it('keeps safe messages and hides raw browser messages from customers', () => {
    const error = toCameraError(new DOMException('sensitive-device-detail', 'NotAllowedError'))
    expect(error.safeMessage).not.toContain('sensitive-device-detail')
    expect(error.code).toBe('CAMERA_PERMISSION_DENIED')
  })
})

describe('camera availability', () => {
  it('reports INSECURE_CONTEXT when not a secure context', () => {
    setSecureContext(false)
    expect(checkCameraAvailability()).toEqual({ ok: false, errorCode: 'INSECURE_CONTEXT' })
  })

  it('reports CAMERA_API_UNAVAILABLE when mediaDevices is missing', () => {
    setSecureContext(true)
    removeMediaDevices()
    expect(checkCameraAvailability()).toEqual({ ok: false, errorCode: 'CAMERA_API_UNAVAILABLE' })
  })

  it('reports ok when the environment is usable', () => {
    setSecureContext(true)
    setupMediaEnvironment()
    expect(checkCameraAvailability()).toEqual({ ok: true })
  })
})

describe('safe track settings', () => {
  it('keeps only non-identifying settings', () => {
    const { stream } = createFakeStream({
      facingMode: 'environment',
      width: 1280,
      height: 720,
      frameRate: 30,
    })
    const settings = extractSafeSettings(stream.getVideoTracks()[0])
    expect(settings).toEqual({
      facingMode: 'environment',
      width: 1280,
      height: 720,
      frameRate: 30,
      aspectRatio: 1280 / 720,
    })
    expect(settings).not.toHaveProperty('deviceId')
    expect(settings).not.toHaveProperty('groupId')
  })

  it('returns an empty object when getSettings throws', () => {
    const { stream } = createFakeStream()
    stream.getVideoTracks()[0].getSettings = () => {
      throw new Error('unsupported')
    }
    expect(extractSafeSettings(stream.getVideoTracks()[0])).toEqual({})
  })
})

describe('requestCameraStream', () => {
  it('requests a stream with audio disabled and safe settings', async () => {
    const { mediaDevices } = setupMediaEnvironment()
    mediaDevices.getUserMedia.mockResolvedValue(createFakeStream({ facingMode: 'user' }).stream)
    const session = await requestCameraStream({ facingMode: 'user' })
    expect(session.settings.facingMode).toBe('user')
    expect(mediaDevices.getUserMedia.mock.calls[0][0].audio).toBe(false)
    expect(session.track).toBeDefined()
    session.stop()
  })

  it('throws CAMERA_NOT_FOUND when no video track exists', async () => {
    const { mediaDevices } = setupMediaEnvironment()
    const streamWithoutVideo = {
      getVideoTracks: () => [],
      getTracks: () => [],
    } as unknown as MediaStream
    mediaDevices.getUserMedia.mockResolvedValue(streamWithoutVideo)
    await expect(requestCameraStream({ facingMode: 'user' })).rejects.toMatchObject({
      code: 'CAMERA_NOT_FOUND',
    })
  })
})

describe('video readiness and scheduling features', () => {
  it('reports a video as not ready when dimensions are zero', () => {
    const env = setupMediaEnvironment()
    env.video.width = 0
    env.video.height = 0
    const video = document.createElement('video')
    expect(isVideoReady(video)).toBe(false)
  })

  it('feature-detects requestVideoFrameCallback', () => {
    setupMediaEnvironment({ useRvf: true })
    expect(supportsRequestVideoFrameCallback(document.createElement('video'))).toBe(true)
  })

  it('does not claim rVFC support when the API is absent', () => {
    setupMediaEnvironment({ useRvf: false })
    expect(supportsRequestVideoFrameCallback(document.createElement('video'))).toBe(false)
  })
})

describe('captureBurst', () => {
  it('fails with VIDEO_NOT_READY before the video has dimensions', async () => {
    const { video } = setupMediaEnvironment()
    video.width = 0
    video.height = 0
    const videoEl = document.createElement('video')
    const canvasEl = document.createElement('canvas')
    await expect(
      captureBurst({
        video: videoEl,
        canvas: canvasEl,
        frameCount: 8,
        durationMs: 1200,
        minimumSuccessfulFrames: 6,
        mimeType: 'image/jpeg',
        quality: 0.95,
      }),
    ).rejects.toMatchObject({ code: 'VIDEO_NOT_READY' })
  })

  it('captures 8 frames via requestVideoFrameCallback', async () => {
    const media = setupMediaEnvironment({ useRvf: true })
    const result = await captureBurst({
      video: document.createElement('video'),
      canvas: document.createElement('canvas'),
      frameCount: 8,
      durationMs: 1200,
      minimumSuccessfulFrames: 6,
      mimeType: 'image/jpeg',
      quality: 0.95,
    })
    expect(result.frames).toHaveLength(8)
    expect(result.scheduler).toBe('rvf')
    expect(media.canvas.toBlob).toHaveBeenCalledTimes(8)
    expect(media.canvas.drawImage).toHaveBeenCalledTimes(8)
  })

  it('captures 8 frames via the requestAnimationFrame fallback', async () => {
    setupMediaEnvironment({ useRvf: false })
    const result = await captureBurst({
      video: document.createElement('video'),
      canvas: document.createElement('canvas'),
      frameCount: 8,
      durationMs: 1200,
      minimumSuccessfulFrames: 6,
      mimeType: 'image/jpeg',
      quality: 0.95,
    })
    expect(result.frames).toHaveLength(8)
    expect(result.scheduler).toBe('rAF')
  })

  it('tolerates partial failures within the minimum threshold', async () => {
    const media = setupMediaEnvironment()
    media.canvas.setToBlob((index) =>
      index === 3 || index === 6 ? null : new Blob(['x'], { type: 'image/jpeg' }),
    )
    const result = await captureBurst({
      video: document.createElement('video'),
      canvas: document.createElement('canvas'),
      frameCount: 8,
      durationMs: 1200,
      minimumSuccessfulFrames: 6,
      mimeType: 'image/jpeg',
      quality: 0.95,
    })
    // 8 ticks, frames 3 and 6 fail → 6 successes (the minimum).
    expect(result.frames).toHaveLength(6)
  })

  it('throws INSUFFICIENT_FRAMES when fewer than the minimum succeed', async () => {
    const media = setupMediaEnvironment()
    media.canvas.setToBlob(() => null)
    await expect(
      captureBurst({
        video: document.createElement('video'),
        canvas: document.createElement('canvas'),
        frameCount: 8,
        durationMs: 1200,
        minimumSuccessfulFrames: 6,
        mimeType: 'image/jpeg',
        quality: 0.95,
      }),
    ).rejects.toMatchObject({ code: 'INSUFFICIENT_FRAMES' })
  })

  it('throws FRAME_CAPTURE_FAILED when the canvas context is unavailable', async () => {
    const media = setupMediaEnvironment()
    media.canvas.setGetContextNull(true)
    await expect(
      captureBurst({
        video: document.createElement('video'),
        canvas: document.createElement('canvas'),
        frameCount: 8,
        durationMs: 1200,
        minimumSuccessfulFrames: 6,
        mimeType: 'image/jpeg',
        quality: 0.95,
      }),
    ).rejects.toMatchObject({ code: 'FRAME_CAPTURE_FAILED' })
  })

  it('honours an abort signal as CAMERA_INTERRUPTED', async () => {
    setupMediaEnvironment()
    const controller = new AbortController()
    controller.abort()
    await expect(
      captureBurst({
        video: document.createElement('video'),
        canvas: document.createElement('canvas'),
        frameCount: 8,
        durationMs: 1200,
        minimumSuccessfulFrames: 6,
        mimeType: 'image/jpeg',
        quality: 0.95,
        signal: controller.signal,
      }),
    ).rejects.toMatchObject({ code: 'CAMERA_INTERRUPTED' })
  })
})

describe('representative frame selection', () => {
  const frame = (id: string): CaptureFrame =>
    ({
      id,
      sequence: 0,
      capturedAtMs: 0,
      blob: new Blob(['x']),
      mimeType: 'image/jpeg',
      width: 1,
      height: 1,
      byteSize: 1,
    }) as CaptureFrame

  it('selects the middle frame deterministically', () => {
    const frames = [frame('a'), frame('b'), frame('c'), frame('d'), frame('e')]
    expect(selectRepresentativeFrame(frames).id).toBe('c')
  })

  it('throws on an empty burst', () => {
    expect(() => selectRepresentativeFrame([])).toThrow()
  })
})

describe('createCaptureBundle', () => {
  it('builds a bundle with a representative frame and config version', () => {
    const frames: CaptureFrame[] = [1, 2, 3, 4, 5].map((n) => ({
      id: `f${n}`,
      sequence: n,
      capturedAtMs: n,
      blob: new Blob(['x']),
      mimeType: 'image/jpeg',
      width: 100,
      height: 100,
      byteSize: 1,
    }))
    const bundle = createCaptureBundle({ frames, camera: { facingMode: 'user' } })
    expect(bundle.captureConfigVersion).toBe('capture-v1')
    expect(bundle.representativeFrameId).toBe('f3')
    expect(bundle.camera).toEqual({ facingMode: 'user' })
    expect(bundle.captureId).toBeTruthy()
    expect(bundle.createdAt).toBeTruthy()
  })
})
