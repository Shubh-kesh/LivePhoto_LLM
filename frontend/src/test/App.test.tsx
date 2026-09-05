import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import App from '../app/App'
import { getInfo } from '../api/info'

vi.mock('../api/info', () => ({
  getInfo: vi.fn(),
}))

const mockedGetInfo = vi.mocked(getInfo)

describe('App routing', () => {
  it('renders the home page at /', async () => {
    mockedGetInfo.mockResolvedValue({ name: 'LivePhoto', version: '0.1.0', environment: 'test' })
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: 'LivePhoto' })).toBeInTheDocument()
    expect(await screen.findByText('Foundation environment ready.')).toBeInTheDocument()
  })

  it('renders the not-found page for unknown routes', async () => {
    mockedGetInfo.mockResolvedValue({ name: 'LivePhoto', version: '0.1.0', environment: 'test' })
    render(
      <MemoryRouter initialEntries={['/does-not-exist']}>
        <App />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })
})
