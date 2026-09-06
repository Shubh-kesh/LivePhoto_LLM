#!/usr/bin/env node
/**
 * Generates a synthetic .y4m video used as the fake camera input for Playwright E2E
 * (M3 §89, §100; M4 §148).
 *
 * The frame content is seeded high-frequency noise in a mid-luminance range: mid-range mean (no
 * dark/bright clipping), high contrast, and high Laplacian sharpness even after the browser's
 * bilinear upscale/downscale (a block checkerboard becomes smooth ramps and would be flagged as
 * blurred by the M3 sharpness metric). The seed is fixed so the output is byte-deterministic.
 *
 * Output: e2e/.fixtures/camera.y4m (gitignored; generated at test time, not committed).
 * Non-sensitive synthetic content only.
 */

import { mkdirSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const width = 320
const height = 240
const frames = 120
const fps = 30
const LOW = 60
const HIGH = 200

const outDir = join(dirname(fileURLToPath(import.meta.url)), '.fixtures')
mkdirSync(outDir, { recursive: true })
const outPath = join(outDir, 'camera.y4m')

// Deterministic PRNG (mulberry32) so the fixture is reproducible across runs.
function mulberry32(seed) {
  let a = seed >>> 0
  return function () {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const random = mulberry32(0x5eed1234)

const yPlane = Buffer.alloc(width * height)
for (let i = 0; i < yPlane.length; i += 1) {
  yPlane[i] = Math.round(LOW + random() * (HIGH - LOW))
}
const chromaPlane = Buffer.alloc((width * height) / 4, 128)

const header = Buffer.from(`YUV4MPEG2 W${width} H${height} F${fps}:1 Ip A1:1 C420jpeg\n`)
const frameMarker = Buffer.from('FRAME\n')

const chunks = [header]
for (let i = 0; i < frames; i += 1) {
  chunks.push(frameMarker, yPlane, chromaPlane, chromaPlane)
}

writeFileSync(outPath, Buffer.concat(chunks))
console.log(`wrote ${outPath} (${width}x${height}, ${frames} frames @ ${fps}fps)`)
