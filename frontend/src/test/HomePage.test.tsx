import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { HomePage } from '../pages/HomePage'
import { getInfo } from '../api/info'
import { renderWithProviders } from './utils'

vi.mock('../api/info', () => ({
  getInfo: vi.fn(),
}))

const mockedGetInfo = vi.mocked(getInfo)

describe('HomePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows the foundation shell', () => {
    mockedGetInfo.mockResolvedValue({ name: 'LivePhoto', version: '0.1.0', environment: 'test' })
    renderWithProviders(<HomePage />)
    expect(screen.getByRole('heading', { name: 'LivePhoto' })).toBeInTheDocument()
    expect(screen.getByText('Secure passive liveness platform')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Go to camera capture' })).toHaveAttribute(
      'href',
      '/capture',
    )
  })

  it('renders application info when available', async () => {
    mockedGetInfo.mockResolvedValue({ name: 'LivePhoto', version: '0.1.0', environment: 'test' })
    renderWithProviders(<HomePage />)
    expect(await screen.findByText('0.1.0')).toBeInTheDocument()
    expect(screen.getByText('test')).toBeInTheDocument()
  })

  it('renders a safe error state when the request fails', async () => {
    mockedGetInfo.mockRejectedValue(new Error('Unable to reach the service'))
    renderWithProviders(<HomePage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load application info')
  })
})
