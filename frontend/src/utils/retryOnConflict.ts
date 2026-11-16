// MariaDB rolls back a whole request when it picks it as the loser of a deadlock, and
// Frappe answers 508: a concurrent transaction was in the way, try again. Nothing from the
// failed request was saved, so asking again is safe for every method.
const CONFLICT_STATUS = 508
const RETRIES = 2

type Options = { onError?: (error: unknown) => void } & Record<string, unknown>

export function retryOnConflict<Fetcher extends (options: any) => Promise<any>>(
  fetcher: Fetcher,
  wait: (ms: number) => Promise<void> = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
): Fetcher {
  async function fetchWithRetry(options: Options) {
    for (let attempt = 0; ; attempt++) {
      const last = attempt >= RETRIES
      try {
        // Only the final attempt may report the failure to the caller.
        return await fetcher(last ? options : { ...options, onError: undefined })
      } catch (error) {
        if (!last && (error as { status?: number })?.status === CONFLICT_STATUS) {
          await wait(150 + Math.random() * 350)
          continue
        }
        if (!last) options.onError?.(error)
        throw error
      }
    }
  }
  return fetchWithRetry as unknown as Fetcher
}
