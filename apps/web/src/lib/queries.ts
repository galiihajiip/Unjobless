import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { useToast } from '@/components/ui'
import { ApiError, get } from './api'

export function useGet<T>(key: QueryKey, path: string | null, opts: { refetchInterval?: number | false; enabled?: boolean } = {}) {
  return useQuery({ queryKey: key, queryFn: () => get<T>(path as string), enabled: path !== null && opts.enabled !== false, refetchInterval: opts.refetchInterval })
}

/** Mutation with toast feedback and invalidation of the given query keys. */
export function useAction<TIn, TOut>(fn: (input: TIn) => Promise<TOut>, opts: { invalidate?: QueryKey[]; success?: string | ((out: TOut) => string); onSuccess?: (out: TOut) => void } = {}) {
  const qc = useQueryClient()
  const { notify } = useToast()
  return useMutation({
    mutationFn: fn,
    onSuccess: (out) => {
      for (const k of opts.invalidate ?? []) void qc.invalidateQueries({ queryKey: k })
      if (opts.success) notify(typeof opts.success === 'function' ? opts.success(out) : opts.success)
      opts.onSuccess?.(out)
    },
    onError: (err) => notify(err instanceof ApiError ? err.message : 'Something went wrong.'),
  })
}

export function errorMessage(err: unknown): string | null {
  if (!err) return null
  return err instanceof ApiError ? err.message : 'Something went wrong.'
}
