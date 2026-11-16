<template>
  <div class="flex flex-wrap items-center justify-between gap-3 pb-3">
    <TabButtons v-model="kind" :options="kinds" @update:model-value="applyKind" />
    <form
      v-if="kind !== 'all'"
      class="flex min-w-0 flex-1 justify-end"
      @submit.prevent="applyFilters"
    >
      <Combobox
        v-if="kind === 'user'"
        v-model="target"
        v-model:query="userQuery"
        :open="userPickerOpen"
        :loading="userSearchLoading"
        variant="outline"
        open-on-click
        placeholder="Filter by user"
        aria-label="Filter by user"
        class="w-64"
        :options="userOptions"
        :filterable="false"
        :empty-text="
          userQuery.trim().length === 1
            ? 'Type one more character to search.'
            : 'No users with moderation history match.'
        "
        @update:open="setUserPickerOpen"
        @update:query="updateUserQuery"
        @update:model-value="applyFilters"
      >
        <template #item-prefix="{ item }">
          <Avatar :image="item.image" :label="item.label" size="sm" />
        </template>
      </Combobox>
      <TextInput
        v-else
        v-model="target"
        placeholder="Filter by post ID, press Enter"
        aria-label="Filter by post ID"
        class="w-64"
      />
    </form>
  </div>
  <ErrorMessage
    v-if="error"
    class="py-3"
    :message="extractServerMessage(error) || 'Could not load history'"
  />
  <p v-if="loading" role="status" class="py-6 text-base text-ink-gray-5">Loading history…</p>
  <div v-else-if="items.length" class="border-t border-outline-gray-1" data-testid="history-list">
    <div
      v-for="item in items"
      :key="item.name"
      class="flex gap-3 border-b border-outline-gray-1 py-3 last:border-b-0"
      data-testid="history-row"
    >
      <div class="flex w-7 shrink-0 justify-center pt-0.5">
        <span class="flex size-6 items-center justify-center rounded-full bg-surface-gray-2">
          <span :class="[actionIcon(item.action), 'size-3.5 text-ink-gray-6']" aria-hidden="true" />
        </span>
      </div>
      <div class="min-w-0 flex-1">
        <div class="flex items-baseline justify-between gap-3">
          <p class="truncate text-base text-ink-gray-9">
            <span class="font-medium">{{ item.action }}</span>
            <span class="text-ink-gray-6"> · {{ targetLabel(item) }}</span>
          </p>
          <time
            :datetime="item.creation"
            :title="dayjsLocal(item.creation).format('D MMM YYYY [at] h:mm A')"
            class="shrink-0 text-p-sm text-ink-gray-5"
          >
            {{ dayjsLocal(item.creation).fromNow() }}
          </time>
        </div>
        <p v-if="detailLine(item)" class="mt-1 text-p-sm text-ink-gray-7">{{ detailLine(item) }}</p>
        <p
          v-if="item.reason"
          class="mt-1 whitespace-pre-wrap break-words text-p-sm text-ink-gray-7"
        >
          “{{ item.reason }}”
        </p>
        <div class="mt-1 flex items-center gap-3">
          <p class="text-p-sm text-ink-gray-5">
            by
            {{
              ['Restriction Expired', 'Slow Mode Expired'].includes(item.action)
                ? 'System'
                : useUser(item.owner).full_name
            }}
          </p>
          <Button
            v-if="item.action === 'Author Cleanup' && !item.undone"
            size="sm"
            variant="ghost"
            icon-left="lucide-undo-2"
            :loading="undoing === item.cleanup"
            @click="undoCleanup(item)"
            >Undo cleanup</Button
          >
        </div>
      </div>
    </div>
  </div>
  <ModerationEmpty
    v-else-if="!error"
    icon="lucide-history"
    title="No moderation history"
    description="Hides, removals, bans, slow mode and cleanups are recorded here."
  />
  <ModerationPager
    :previous="start > 0"
    :next="hasMore"
    @previous="changePage(-40)"
    @next="changePage(40)"
  />
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Avatar,
  Button,
  Combobox,
  ErrorMessage,
  TabButtons,
  TextInput,
  call,
  dayjsLocal,
  toast,
} from 'frappe-ui'
import { expiryLabel, restrictionTransition } from '@/data/restrictions'
import { slowModeLabel } from '@/data/slowMode'
import ModerationEmpty from './moderation/ModerationEmpty.vue'
import ModerationPager from './moderation/ModerationPager.vue'
import { useUser } from '@/data/users'
import { extractServerMessage } from '@/utils'

const props = defineProps<{ communityId: string }>()
const route = useRoute()
const router = useRouter()
const kinds = [
  { label: 'All', value: 'all' },
  { label: 'Discussions', value: 'discussion' },
  { label: 'Replies', value: 'reply' },
  { label: 'Users', value: 'user' },
]
const kind = ref('all')
const target = ref('')
const userQuery = ref('')
const userPickerOpen = ref(false)
const userSearchLoading = ref(false)
const userHasMore = ref(false)
const userCursor = ref('')
const userOptions = ref<{ label: string; value: string; image: string | null }[]>([])
let userSearchRequest = 0
let userSearchTimer: ReturnType<typeof setTimeout> | undefined
const start = ref(0)
const loading = ref(false)
const error = ref<unknown>(null)
const hasMore = ref(false)
type HistoryItem = {
  name: string
  action: string
  owner: string
  creation: string
  previous_expires_at?: string
  expires_at?: string
  previous_slow_mode_seconds?: number
  slow_mode_seconds?: number
  reason?: string
  discussion?: string
  comment?: string
  user?: string
  title?: string
  cleanup?: string
  undone?: boolean
}
const items = ref<HistoryItem[]>([])
function targetLabel(item: HistoryItem) {
  if (item.comment) return `Reply #${item.comment}`
  if (item.discussion) return `Discussion #${item.discussion}`
  return useUser(item.user).full_name
}
function applyFilters() {
  router.replace({
    query: {
      ...route.query,
      tab: 'history',
      kind: kind.value,
      target:
        kind.value === 'all'
          ? undefined
          : kind.value === 'user'
            ? target.value || userQuery.value.trim() || undefined
            : target.value || undefined,
    },
  })
}
const undoing = ref('')
const icons: Record<string, string> = {
  Hide: 'lucide-eye-off',
  'Delete Spam': 'lucide-trash-2',
  Restore: 'lucide-rotate-ccw',
  Ban: 'lucide-user-x',
  'Ban Changed': 'lucide-user-x',
  Unban: 'lucide-user-check',
  'Restriction Expired': 'lucide-clock',
  'Slow Mode Changed': 'lucide-timer',
  'Slow Mode Expired': 'lucide-clock',
  'Author Cleanup': 'lucide-eraser',
  'Undo Cleanup': 'lucide-undo-2',
}
const actionIcon = (action: string) => icons[action] || 'lucide-shield'
function detailLine(item: HistoryItem) {
  if (['Slow Mode Changed', 'Slow Mode Expired'].includes(item.action)) {
    const change = `${slowModeLabel(item.previous_slow_mode_seconds)} → ${slowModeLabel(item.slow_mode_seconds)}`
    if (item.action === 'Slow Mode Changed' && item.slow_mode_seconds)
      return `${change} · ${item.expires_at ? `ends ${expiryLabel(item.expires_at)}` : 'until turned off'}`
    return change
  }
  if (['Ban', 'Ban Changed', 'Unban', 'Restriction Expired'].includes(item.action))
    return restrictionTransition(item)
  if (['Author Cleanup', 'Undo Cleanup'].includes(item.action)) return item.title || 'In progress'
  return ''
}
function applyKind() {
  target.value = ''
  applyFilters()
}
async function undoCleanup(item: HistoryItem) {
  undoing.value = item.cleanup || ''
  try {
    await call('gameplan.author_cleanup.undo', { cleanup: item.cleanup })
    item.undone = true
    toast.success('Undo started. The result appears in History.')
  } catch (e) {
    toast.error(extractServerMessage(e) || 'Could not undo the cleanup')
  } finally {
    undoing.value = ''
  }
}
let request = 0
async function load() {
  const current = ++request
  items.value = []
  error.value = null
  loading.value = true
  try {
    const result = await call<{ items: HistoryItem[]; has_more: boolean }>(
      'gameplan.moderation_history.history',
      {
        community: props.communityId,
        kind: route.query.kind || 'all',
        target: route.query.target || '',
        start: start.value,
      },
    )
    if (current !== request) return
    items.value = result.items
    hasMore.value = result.has_more
  } catch (e) {
    if (current === request) error.value = e
  } finally {
    if (current === request) loading.value = false
  }
}
watch(
  [() => props.communityId, () => route.query.kind, () => route.query.target],
  () => {
    kind.value = kinds.some((option) => option.value === route.query.kind)
      ? String(route.query.kind)
      : 'all'
    target.value =
      typeof route.query.target === 'string' && kind.value !== 'all' ? route.query.target : ''
    start.value = 0
    load()
  },
  { immediate: true },
)
function changePage(delta: number) {
  start.value += delta
  load()
}

async function loadBanHistoryUsers(query: string, request: number, after = '') {
  userSearchLoading.value = true
  try {
    const result = await call<{
      items: { name: string; full_name: string; user_image: string | null }[]
      has_more: boolean
      next_cursor: string
    }>('gameplan.moderation_history.ban_users', {
      community: props.communityId,
      query,
      after,
    })
    if (request !== userSearchRequest || !userPickerOpen.value) return
    const options = result.items.map((user) => ({
      label: user.full_name || user.name,
      value: user.name,
      image: user.user_image,
    }))
    userOptions.value = after ? [...userOptions.value, ...options] : options
    userHasMore.value = result.has_more
    userCursor.value = result.next_cursor
  } catch (e) {
    if (request === userSearchRequest) error.value = e
  } finally {
    if (request === userSearchRequest) userSearchLoading.value = false
  }
}

watch(
  [userQuery, userPickerOpen, () => props.communityId, kind],
  ([query, open, , selectedKind]) => {
    const request = ++userSearchRequest
    clearTimeout(userSearchTimer)
    userSearchLoading.value = false
    if (!open || selectedKind !== 'user') return

    const term = query.trim()
    userOptions.value = []
    userHasMore.value = false
    userCursor.value = ''
    if (term.length === 1) return

    userSearchTimer = setTimeout(() => loadBanHistoryUsers(term, request), term ? 250 : 0)
  },
)

function setUserPickerOpen(open: boolean) {
  userPickerOpen.value = open
}

function updateUserQuery(query: string) {
  userQuery.value = query
  const selected = userOptions.value.find((option) => option.value === target.value)
  if (target.value && selected?.label !== query) target.value = ''
}

function loadMoreBanHistoryUsers(event: Event) {
  const viewport = event.target
  if (
    !(viewport instanceof HTMLElement) ||
    !viewport.closest('[data-slot="content"]') ||
    viewport.scrollTop + viewport.clientHeight < viewport.scrollHeight - 24 ||
    !userPickerOpen.value ||
    !userHasMore.value ||
    userSearchLoading.value
  ) {
    return
  }
  loadBanHistoryUsers(userQuery.value.trim(), userSearchRequest, userCursor.value)
}

onMounted(() => document.addEventListener('scroll', loadMoreBanHistoryUsers, true))
onBeforeUnmount(() => document.removeEventListener('scroll', loadMoreBanHistoryUsers, true))
</script>
