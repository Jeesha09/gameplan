import { computed, ref, watch, toValue, type MaybeRefOrGetter } from 'vue'
import { useEventListener, useIntervalFn } from '@vueuse/core'
import { call } from 'frappe-ui'

type PostingStatus = { retry_after: number; limit: string }

export function usePostingLimit(
  kind: 'discussion' | 'reply',
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const deadline = ref(0)
  const now = ref(Date.now())
  const limit = ref('')
  let request = 0
  async function refresh() {
    const current = ++request
    if (!toValue(enabled)) {
      deadline.value = 0
      return
    }
    try {
      const result = await call<PostingStatus>('gameplan.posting_limits.status', { kind })
      if (current !== request) return
      now.value = Date.now()
      deadline.value = now.value + result.retry_after * 1000
      limit.value = result.limit
    } catch {
      // Every submission rechecks the policy on the server.
    }
  }
  watch(() => toValue(enabled), refresh, { immediate: true })
  useEventListener(window, 'focus', refresh)
  useIntervalFn(() => (now.value = Date.now()), 1000)
  const remaining = computed(() => Math.max(0, Math.ceil((deadline.value - now.value) / 1000)))
  const message = computed(() =>
    remaining.value
      ? `Posting limit: ${limit.value}. You can post again in ${remaining.value}s. You can keep editing your draft.`
      : '',
  )
  return { remaining, message, refresh }
}
