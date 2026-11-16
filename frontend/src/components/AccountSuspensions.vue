<template>
  <div class="text-ink-gray-9">
    <p class="pb-5 text-p-base text-ink-gray-6">
      Silenced accounts can sign in and read, but can't post anywhere. Suspended accounts can't sign
      in or use the site, its apps, or API access.
    </p>
    <div class="flex flex-wrap items-center gap-2 pb-3">
      <Combobox
        v-model="chosen"
        v-model:query="query"
        placeholder="Find an account by name or email"
        aria-label="Account"
        class="w-full max-w-sm"
        open-on-click
        :options="options"
        :filterable="false"
        :loading="searching && !options.length"
        :empty-text="
          query.trim().length === 1
            ? 'Type one more character to search the site.'
            : 'No eligible users match this search.'
        "
        @update:open="pickerOpen = $event"
      >
        <template #item-prefix="{ item }"
          ><Avatar :image="item.image" :label="item.label" size="sm"
        /></template>
        <template #footer>
          <Button
            v-if="candidateCursor"
            variant="ghost"
            class="w-full"
            :loading="searching"
            @click="search(candidateCursor)"
          >
            Load more users
          </Button>
        </template>
      </Combobox>
      <template v-if="chosen">
        <Button variant="solid" icon-left="lucide-shield-ban" @click="edit({ user: chosen })"
          >Restrict</Button
        >
        <Button @click="cleanupOpen = true">Remove all posts</Button>
        <Button variant="ghost" @click="showHistory({ user: chosen })">History</Button>
      </template>
      <p v-else class="ml-auto text-p-sm text-ink-gray-6">
        {{
          items.length ? `${items.length}${nextCursor ? '+' : ''} active` : 'No active restrictions'
        }}
      </p>
    </div>
    <ErrorMessage
      v-if="error"
      class="py-3"
      :message="extractServerMessage(error) || 'Could not load restrictions'"
    />
    <p v-if="loading" role="status" class="py-6 text-base text-ink-gray-5">Loading restrictions…</p>
    <div v-else-if="items.length" class="border-t border-outline-gray-1">
      <ModerationRow v-for="item in items" :key="item.user">
        <template #lead>
          <Avatar :image="item.user_image" :label="item.full_name || item.user" size="md" />
        </template>
        <template #title>{{ item.full_name || item.user }}</template>
        <template v-if="item.reason" #detail>{{ item.reason }}</template>
        <template #meta>{{ untilLabel(item.expires_at) }}</template>
        <template #status>
          <Badge :label="item.kind === 'Silence' ? 'Silenced' : 'Suspended'" />
        </template>
        <template #actions>
          <Button variant="subtle" @click="edit(item, true)">Lift</Button>
          <Dropdown
            align="end"
            :button="{ icon: 'lucide-more-horizontal', variant: 'ghost', label: 'More actions' }"
            :options="[
              { label: 'Change restriction', icon: 'lucide-pencil', onClick: () => edit(item) },
              {
                label: 'Remove all posts',
                icon: 'lucide-trash-2',
                onClick: () => {
                  chosen = item.user
                  cleanupOpen = true
                },
              },
              { label: 'View history', icon: 'lucide-history', onClick: () => showHistory(item) },
            ]"
          />
        </template>
      </ModerationRow>
    </div>
    <ModerationEmpty
      v-else-if="!error"
      icon="lucide-shield-check"
      title="No accounts are restricted"
      description="Silence or suspend an account across every Community on this site."
    />
    <ModerationPager
      :previous="cursors.length > 0"
      :next="!!nextCursor"
      @previous="previous"
      @next="next"
    />
    <CleanupDialog
      v-if="cleanupOpen"
      v-model:open="cleanupOpen"
      :user="chosen"
      :label="useUser(chosen).full_name || chosen"
    />
    <RestrictionDialog
      v-if="selected"
      :key="`${selected.user}-${lifting}`"
      v-model:open="dialogOpen"
      :user="selected"
      :lifting="lifting"
      @saved="saved"
    />
    <Dialog v-model:open="historyOpen" title="Account history">
      <ScrollArea class="h-96" viewport-class="h-96 pr-3">
        <div v-for="row in history" :key="row.name" class="border-b border-outline-gray-2 py-4">
          <p class="text-base-medium">
            {{ row.action }} ·
            {{ systemActions.includes(row.action) ? 'System' : useUser(row.owner).full_name }}
          </p>
          <p class="mt-1 text-p-sm text-ink-gray-6">
            {{ dayjsLocal(row.creation).format('D MMM YYYY, h:mm A z') }}
          </p>
          <p class="mt-2 whitespace-pre-wrap text-base">{{ row.reason }}</p>
          <p class="mt-2 text-base text-ink-gray-6">
            {{ row.level ? levelTransition(row) : restrictionTransition(row) }}
          </p>
        </div>
        <Button v-if="historyCursor" @click="loadHistory(historyCursor)">More history</Button>
      </ScrollArea>
    </Dialog>
  </div>
</template>
<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Avatar,
  Badge,
  Button,
  Combobox,
  Dialog,
  Dropdown,
  ScrollArea,
  ErrorMessage,
  call,
  dayjsLocal,
} from 'frappe-ui'
import CleanupDialog from './CleanupDialog.vue'
import ModerationEmpty from './moderation/ModerationEmpty.vue'
import ModerationPager from './moderation/ModerationPager.vue'
import ModerationRow from './moderation/ModerationRow.vue'
import RestrictionDialog from './RestrictionDialog.vue'
import { restrictionTransition, untilLabel, type RestrictionUser } from '@/data/restrictions'
import { extractServerMessage } from '@/utils'
import { useUser } from '@/data/users'
const items = ref<RestrictionUser[]>([])
const loading = ref(false),
  searching = ref(false),
  pickerOpen = ref(false)
const error = ref<unknown>(null),
  chosen = ref(''),
  query = ref(''),
  cleanupOpen = ref(false)
const options = ref<{ label: string; value: string; image?: string }[]>([])
const cursor = ref(''),
  nextCursor = ref(''),
  cursors = ref<string[]>([]),
  candidateCursor = ref('')
const selected = ref<RestrictionUser | null>(null),
  lifting = ref(false),
  dialogOpen = ref(false)
const historyOpen = ref(false),
  historyUser = ref(''),
  historyCursor = ref('')
type HistoryItem = {
  name: string
  action: string
  owner: string
  creation: string
  reason?: string
  expires_at?: string
  previous_expires_at?: string
  previous_level?: string
  level?: string
}
const systemActions = ['Restriction Expired', 'Regular Promotion', 'Regular Demotion']
function levelTransition(row: HistoryItem) {
  if (['Level Locked', 'Level Unlocked'].includes(row.action)) return `Level ${row.level}`
  return `${row.previous_level || 'New'} → ${row.level}`
}
type Page<T> = { items: T[]; has_more: boolean; next_cursor: string }
type Candidate = { name: string; full_name: string; user_image?: string }
const history = ref<HistoryItem[]>([])
let candidateViewport: HTMLElement | null = null
let searchRequest = 0
let timer: ReturnType<typeof setTimeout>
watch([query, pickerOpen], () => {
  const request = ++searchRequest
  clearTimeout(timer)
  searching.value = false
  candidateViewport = null
  options.value = []
  candidateCursor.value = ''
  if (pickerOpen.value && query.value.trim().length !== 1)
    timer = setTimeout(() => search('', request), query.value ? 250 : 0)
})
async function search(after = '', request = searchRequest) {
  const viewport = after ? candidateViewport : null
  const scrollTop = viewport?.scrollTop || 0
  searching.value = true
  try {
    const data = await call<Page<Candidate>>('gameplan.restriction_queries.candidates', {
      query: query.value,
      after,
    })
    if (request !== searchRequest) return
    const result = data.items.map((u) => ({
      label: u.full_name || u.name,
      value: u.name,
      image: u.user_image,
    }))
    options.value = after ? [...options.value, ...result] : result
    candidateCursor.value = data.next_cursor
    if (viewport) {
      // Remove after upgrading to a release containing frappe/frappe-ui#1341.
      await nextTick()
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
      if (request === searchRequest && pickerOpen.value && viewport.isConnected)
        viewport.scrollTop = scrollTop
    }
  } catch (e) {
    if (request === searchRequest) error.value = e
  } finally {
    if (request === searchRequest) searching.value = false
  }
}
async function load() {
  loading.value = true
  try {
    const data = await call<Page<RestrictionUser>>(
      'gameplan.restriction_queries.account_suspensions',
      {
        after: cursor.value,
      },
    )
    items.value = data.items
    nextCursor.value = data.next_cursor
  } catch (e) {
    error.value = e
  } finally {
    loading.value = false
  }
}
function edit(user: RestrictionUser, lift = false) {
  selected.value = user
  lifting.value = lift
  dialogOpen.value = true
}
function next() {
  cursors.value.push(cursor.value)
  cursor.value = nextCursor.value
  load()
}
function previous() {
  cursor.value = cursors.value.pop() || ''
  load()
}
function saved() {
  chosen.value = ''
  selected.value = null
  load()
}
async function showHistory(user: RestrictionUser) {
  historyUser.value = user.user
  history.value = []
  historyOpen.value = true
  await loadHistory()
}
async function loadHistory(before = '') {
  try {
    const data = await call<Page<HistoryItem>>('gameplan.restriction_queries.account_history', {
      user: historyUser.value,
      before,
    })
    history.value = before ? [...history.value, ...data.items] : data.items
    historyCursor.value = data.next_cursor
  } catch (e) {
    error.value = e
  }
}
function moreCandidatesOnScroll(event: Event) {
  const element = event.target
  if (
    !pickerOpen.value ||
    !(element instanceof HTMLElement) ||
    !element.hasAttribute('data-reka-combobox-viewport')
  )
    return
  candidateViewport = element
  if (searching.value || !candidateCursor.value) return
  if (element.scrollHeight - element.scrollTop - element.clientHeight < 48)
    search(candidateCursor.value)
}

onMounted(() => {
  load()
  document.addEventListener('scroll', moreCandidatesOnScroll, true)
})
onBeforeUnmount(() => {
  clearTimeout(timer)
  searchRequest++
  document.removeEventListener('scroll', moreCandidatesOnScroll, true)
})
</script>
