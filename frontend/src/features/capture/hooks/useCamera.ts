/**
 * useCamera — camera session lifecycle hook (M2 §14-17, §48, §53).
 *
 * Owns the MediaStream/CameraSession lifecycle: start, switch, stop, stale-request guarding and
 * unexpected track termination. The video element is owned by the caller (videoRef) so attaching
 * the stream stays a component concern while media access stays here.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'

import { requestCameraStream } from '../media/camera'
import type { CameraSession, FacingMode, SafeTrackSettings } from '../types/camera'
import { CameraError, toCameraError } from '../media/mediaErrors'

export interface UseCameraOptions {
  videoRef: RefObject<HTMLVideoElement | null>
  onTrackEnded?: () => void
}

export interface UseCameraResult {
  session: CameraSession | null
  settings: SafeTrackSettings
  canSwitch: boolean
  error: CameraError | null
  start: (facingMode?: FacingMode) => Promise<void>
  switchCamera: () => Promise<void>
  stop: () => void
  /** Whether a camera session is currently active (ref-backed, for async flow decisions). */
  isActive: () => boolean
}

export function useCamera({ videoRef, onTrackEnded }: UseCameraOptions): UseCameraResult {
  const [session, setSession] = useState<CameraSession | null>(null)
  const [settings, setSettings] = useState<SafeTrackSettings>({})
  const [canSwitch, setCanSwitch] = useState(false)
  const [error, setError] = useState<CameraError | null>(null)

  const sessionRef = useRef<CameraSession | null>(null)
  const generationRef = useRef(0)
  const intentionalStopRef = useRef(false)
  const onTrackEndedRef = useRef(onTrackEnded)
  onTrackEndedRef.current = onTrackEnded

  const attachAndPlay = useCallback(
    async (next: CameraSession): Promise<void> => {
      const video = videoRef.current
      if (!video) {
        next.stop()
        throw new CameraError('CAMERA_START_FAILED')
      }
      video.srcObject = next.stream
      await new Promise<void>((resolve, reject) => {
        const onLoaded = () => {
          video.removeEventListener('loadedmetadata', onLoaded)
          resolve()
        }
        video.addEventListener('loadedmetadata', onLoaded)
        window.setTimeout(() => {
          video.removeEventListener('loadedmetadata', onLoaded)
          reject(new CameraError('CAMERA_START_FAILED'))
        }, 5000)
      })
      try {
        await video.play()
      } catch (playError) {
        next.stop()
        throw toCameraError(playError)
      }
    },
    [videoRef],
  )

  const wireTrackEnded = useCallback((next: CameraSession): void => {
    next.track.addEventListener('ended', () => {
      if (intentionalStopRef.current) return
      onTrackEndedRef.current?.()
    })
  }, [])

  const adoptSession = useCallback(
    async (next: CameraSession): Promise<void> => {
      await attachAndPlay(next)
      intentionalStopRef.current = false
      wireTrackEnded(next)
      if (sessionRef.current) {
        intentionalStopRef.current = true
        sessionRef.current.stop()
      }
      sessionRef.current = next
      setSession(next)
      setSettings(next.settings)
      setCanSwitch(await detectCanSwitchCamera())
    },
    [attachAndPlay, wireTrackEnded],
  )

  const start = useCallback(
    async (facingMode: FacingMode = 'user'): Promise<void> => {
      const generation = ++generationRef.current
      setError(null)
      try {
        const next = await requestCameraStream({ facingMode })
        if (generation !== generationRef.current) {
          // A newer request superseded this one: never let the stale stream become active (M2 §53).
          next.stop()
          return
        }
        await adoptSession(next)
        if (generation !== generationRef.current) {
          next.stop()
          return
        }
      } catch (caught) {
        if (generation !== generationRef.current) return
        const cameraError = toCameraError(caught)
        setError(cameraError)
        throw cameraError
      }
    },
    [adoptSession],
  )

  const switchCamera = useCallback(async (): Promise<void> => {
    const previousFacing: FacingMode =
      sessionRef.current?.settings.facingMode === 'environment' ? 'environment' : 'user'
    const nextMode: FacingMode = previousFacing === 'environment' ? 'user' : 'environment'
    const generation = ++generationRef.current
    setError(null)

    // M3 §76: stop the previous camera FIRST so no two camera streams are required to be open
    // concurrently (safer mobile compatibility).
    const previous = sessionRef.current
    if (previous) {
      intentionalStopRef.current = true
      previous.stop()
    }
    sessionRef.current = null
    setSession(null)
    if (videoRef.current) {
      videoRef.current.srcObject = null
    }

    try {
      const next = await requestCameraStream({ facingMode: nextMode })
      if (generation !== generationRef.current) {
        next.stop()
        return
      }
      await adoptSession(next)
      if (generation !== generationRef.current) {
        next.stop()
        return
      }
    } catch (caught) {
      if (generation !== generationRef.current) return
      const primaryError = toCameraError(caught)
      // Attempt to reacquire the previous camera (M3 §76). A recovered camera is still a usable
      // stream; the caller surfaces a recoverable message.
      try {
        const recovered = await requestCameraStream({ facingMode: previousFacing })
        if (generation !== generationRef.current) {
          recovered.stop()
          return
        }
        await adoptSession(recovered)
        if (generation !== generationRef.current) {
          recovered.stop()
          return
        }
        throw new CameraError('CAMERA_SWITCH_FAILED')
      } catch (recoveryCaught) {
        if (generation !== generationRef.current) return
        if (recoveryCaught instanceof CameraError) {
          setError(recoveryCaught)
          throw recoveryCaught
        }
        setError(primaryError)
        throw primaryError
      }
    }
  }, [adoptSession, videoRef])

  const stop = useCallback((): void => {
    generationRef.current += 1
    intentionalStopRef.current = true
    if (sessionRef.current) {
      sessionRef.current.stop()
      sessionRef.current = null
    }
    setSession(null)
    if (videoRef.current) {
      videoRef.current.srcObject = null
    }
  }, [videoRef])

  const isActive = useCallback((): boolean => sessionRef.current !== null, [])

  useEffect(() => {
    return () => {
      stop()
    }
  }, [stop])

  return { session, settings, canSwitch, error, start, switchCamera, stop, isActive }
}

/** Best-effort: only offer camera switching when >= 2 videoinput devices exist (M2 §16-17). */
async function detectCanSwitchCamera(): Promise<boolean> {
  try {
    const md = navigator.mediaDevices
    if (md && typeof md.enumerateDevices === 'function') {
      const devices = await md.enumerateDevices()
      return devices.filter((d) => d.kind === 'videoinput').length >= 2
    }
  } catch {
    // Enumeration is an enhancement, not a security control; default to no switch button.
  }
  return false
}
