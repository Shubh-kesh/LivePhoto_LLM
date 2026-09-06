import { QueryClientProvider } from '@tanstack/react-query'
import { Route, Routes } from 'react-router-dom'

import { CapturePage } from '../features/capture/CapturePage'
import { HomePage } from '../pages/HomePage'
import { NotFoundPage } from '../pages/NotFoundPage'
import { ErrorBoundary } from './ErrorBoundary'
import { queryClient } from './queryClient'

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/capture" element={<CapturePage />} />
          <Route path="/dev/vlm-experiment" element={<CapturePage experiment />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
