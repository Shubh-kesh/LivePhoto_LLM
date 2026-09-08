// Stub consuming-application callback server for M5.8 E2E (test only).
// Accepts the LivePhoto callback POST and returns an approved redirect URL.
import { createServer } from 'node:http'

const REDIRECT_URL = 'http://localhost:3001/complete'

const server = createServer((req, res) => {
  if (req.method === 'POST' && req.url.startsWith('/livephoto/callback')) {
    let body = ''
    req.on('data', (chunk) => (body += chunk))
    req.on('end', () => {
      // Never log the body (it contains Base64 image data).
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ redirect_url: REDIRECT_URL }))
    })
    return
  }
  res.writeHead(200, { 'Content-Type': 'text/plain' })
  res.end('stub-consumer')
})

server.listen(3001, '127.0.0.1', () => {
  console.log('[stub-consumer] listening on http://localhost:3001')
})
