import { useQuery } from '@tanstack/react-query'

import { getInfo } from '../api/info'

export function useInfo() {
  return useQuery({
    queryKey: ['info'],
    queryFn: getInfo,
    staleTime: 5 * 60 * 1000,
  })
}
