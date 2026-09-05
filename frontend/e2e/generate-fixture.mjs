#!/usr/bin/env node
/**
 * Generates a synthetic checkerboard .y4m video used as the fake camera input for Playwright E2E
 * (M3 §89, §100). The checkerboard has mid-range luminance (no dark/bright clipping), sharp edges
 * and high contrast, so the real pixel-quality pipeline deterministically passes M3 thresholds.
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
const block = 16
const dark = 80
const bright = 180

const outDir = join(dirname(fileURLToPath(import.meta.url)), '.fixtures')
mkdirSync(outDir, { recursive: true })
const outPath = join(outDir, 'camera.y4m')

const yPlane = Buffer.alloc(width * height)
for (let y = 0; y < height; y += 1) {
  for (let x = 0; x < width; x += 1) {
    const cell = Math.floor(x / block) + Math.floor(y / block)
    yPlane[y * width + x] = cell % 2 === 0 ? dark : bright
  }
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
