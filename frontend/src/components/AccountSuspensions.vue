<template>
  <div class="text-ink-gray-9">
    <p class="pb-5 text-p-base text-ink-gray-6">
      Silenced accounts can sign in and read, but can't post anywhere. Suspended accounts can't sign
      in or use the site, its apps, or API access.
    </p>
    <Tabs v-model="tab" class="mb-4">
      <TabList variant="underline">
        <TabTrigger value="active" label="Active" />
        <TabTrigger value="history" label="History" />
      </TabList>
    </Tabs>
    <template v-if="tab === 'active'">
      <div class="flex items-center gap-2 pb-3">
        <TextInput
          v-model="activeQuery"
          class="w-full max-w-sm"
          type="text"
          placeholder="Search restricted accounts"
          aria-label="Search restricted accounts"
          :debounce="300"
        >
          <template #prefix><span class="lucide-search w-4 text-ink-gray-5" /></template>
        </TextInput>
        <Button class="ml-auto" variant="solid" icon-left="lucide-shield-ban" @click="startRestrict"
          >Restrict</Button
        >
      </div>
      <ErrorMessage
        v-if="error"
        class="py-3"
        :message="extractServerMessage(error) || 'Could not load restrictions'"
      />
      <p v-if="loading" role="status" class="py-6 text-base text-ink-gray-5">
        Loading restrictions…
      </p>
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
                  onClick: () => removePosts(item),
                },
                { label: 'View history', icon: 'lucide-history', onClick: () => showHistory(item) },
              ]"
            />
          </template>
        </ModerationRow>
      </div>
      <ModerationEmpty
        v-else-if="!error && activeQuery.trim()"
        icon="lucide-search"
        title="No restricted accounts match"
        description="Try a different name or email."
      />
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
    </template>
    <template v-else>
      <div class="pb-3">
        <TextInput
          v-model="siteHistoryQuery"
          class="w-full max-w-sm"
          type="text"
          placeholder="Search history"
          aria-label="Search history"
          :debounce="300"
        >
          <template #prefix><span class="lucide-search w-4 text-ink-gray-5" /></template>
        </TextInput>
      </div>
      <ErrorMessage
        v-if="siteHistoryError"
        class="py-3"
        :message="extractServerMessage(siteHistoryError) || 'Could not load the history'"
      />
      <p
        v-if="siteHistoryLoading && !siteHistory.length"
        role="status"
        class="py-6 text-base text-ink-gray-5"
      >
        Loading history…
      </p>
      <div v-else-if="siteHistory.length" class="border-t border-outline-gray-1">
        <ModerationRow v-for="row in siteHistory" :key="row.name">
          <template #lead>
            <Avatar :image="row.user_image" :label="row.full_name || row.user" size="md" />
          </template>
          <template #title>{{ row.full_name || row.user }}</template>
          <template v-if="row.reason" #detail>{{ row.reason }}</template>
          <template #meta>
            {{ actor(row) }} · {{ dayjsLocal(row.creation).format('D MMM YYYY, h:mm A') }} ·
            {{ restrictionTransition(row) }}
          </template>
          <template #status><Badge :label="actionLabels[row.action] || row.action" /></template>
          <template #actions>
            <Button
              variant="ghost"
              icon="lucide-history"
              :aria-label="`History of ${row.full_name || row.user}`"
              @click="showHistory(row)"
            />
          </template>
        </ModerationRow>
      </div>
      <ModerationEmpty
        v-else-if="!siteHistoryError && siteHistoryQuery.trim()"
        icon="lucide-search"
        title="No history matches"
        description="Try a different name or email."
      />
      <ModerationEmpty
        v-else-if="!siteHistoryError"
        icon="lucide-history"
        title="No restrictions yet"
        description="Every silence, suspension and lift on this site shows here."
      />
      <Button
        v-if="siteHistoryCursor"
        class="mt-3"
        :loading="siteHistoryLoading"
        @click="loadSiteHistory(siteHistoryCursor)"
        >More history</Button
      >
    </template>
    <CleanupDialog
      v-if="cleanupOpen"
      v-model:open="cleanupOpen"
      :user="cleanupUser.user"
      :label="cleanupUser.full_name || cleanupUser.user"
    />
    <RestrictionDialog
      v-if="selected"
      :key="picking ? 'new' : `${selected.user}-${lifting}`"
      v-model:open="dialogOpen"
      :user="selected"
      :lifting="lifting"
      @saved="saved"
    >
      <template v-if="picking" #person>
        <Combobox
          v-model="chosen"
          v-model:query="query"
          label="Account"
          placeholder="Find an account by name or email"
          class="w-full"
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
        </Combobox>
      </template>
    </RestrictionDialog>
    <Dialog v-model:open="historyOpen" title="Account history">
      <ScrollArea class="h-96" viewport-class="h-96 pr-3">
        <!-- An empty or failed load must not look like a blank box: say which it is. -->
        <p
          v-if="historyLoading && !history.length"
          role="status"
          class="py-6 text-base text-ink-gray-5"
        >
          Loading history…
        </p>
        <ErrorMessage
          v-else-if="historyError"
          class="py-3"
          :message="extractServerMessage(historyError) || 'Could not load the history'"
        />
        <ModerationEmpty
          v-else-if="!history.length"
          icon="lucide-history"
          title="No history yet"
          description="Restrictions, trust level changes and badge changes for this account show here."
        />
        <div v-for="row in history" :key="row.name" class="border-b border-outline-gray-2 py-4">
          <p class="text-base-medium text-ink-gray-9">
            {{ row.action }} ·
            {{ systemActions.includes(row.action) ? 'System' : useUser(row.owner).full_name }}
          </p>
          <p class="mt-1 text-p-sm text-ink-gray-6">
            {{ dayjsLocal(row.creation).format('D MMM YYYY, h:mm A z') }}
          </p>
          <p class="mt-2 whitespace-pre-wrap text-base text-ink-gray-8">{{ row.reason }}</p>
          <p class="mt-2 text-base text-ink-gray-6">
            {{
              row.title ? row.title : row.level ? levelTransition(row) : restrictionTransition(row)
            }}
          </p>
        </div>
        <Button v-if="historyCursor" @click="loadHistory(historyCursor)">More history</Button>
      </ScrollArea>
    </Dialog>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Avatar,
  Badge,
  Button,
  Combobox,
  Dialog,
  Dropdown,
  ScrollArea,
  ErrorMessage,
  TabList,
  TabTrigger,
  Tabs,
  TextInput,
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
type Option = { label: string; value: string; image?: string }
const found = ref<Option[]>([])
// The picked account stays in the list after a search clears it. Without it the box has no label
// for the value and shows the raw email.
const picked = ref<Option | null>(null)
const options = computed(() =>
  picked.value && !found.value.some((option) => option.value === picked.value?.value)
    ? [picked.value, ...found.value]
    : found.value,
)
watch(chosen, (value) => {
  picked.value = value
    ? (found.value.find((option) => option.value === value) ?? picked.value)
    : null
  if (picking.value) selected.value = { user: value, full_name: picked.value?.label || '' }
})
const cursor = ref(''),
  nextCursor = ref(''),
  cursors = ref<string[]>([]),
  candidateCursor = ref('')
const selected = ref<RestrictionUser | null>(null),
  lifting = ref(false),
  picking = ref(false),
  dialogOpen = ref(false)
const tab = ref<'active' | 'history'>('active'),
  activeQuery = ref('')
const cleanupUser = ref<{ user: string; full_name?: string }>({ user: '' })
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
  /** The badge, for Badge Granted and Badge Revoked. */
  title?: string
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
  found.value = []
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
    found.value = after ? [...found.value, ...result] : result
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
      { after: cursor.value, query: activeQuery.value },
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
  picking.value = false
  selected.value = user
  lifting.value = lift
  dialogOpen.value = true
}
function startRestrict() {
  chosen.value = ''
  picking.value = true
  selected.value = { user: '' } as RestrictionUser
  lifting.value = false
  dialogOpen.value = true
}
function removePosts(item: RestrictionUser) {
  cleanupUser.value = { user: item.user, full_name: item.full_name }
  cleanupOpen.value = true
}
watch(activeQuery, () => {
  cursor.value = ''
  cursors.value = []
  load()
})
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
  picking.value = false
  selected.value = null
  load()
  siteHistoryLoaded = false
  if (tab.value === 'history') loadSiteHistory()
}
type SiteHistoryItem = HistoryItem & { user: string; full_name?: string; user_image?: string }
const actionLabels: Record<string, string> = {
  Suspend: 'Suspended',
  Silence: 'Silenced',
  'Suspension Changed': 'Suspension changed',
  'Silence Changed': 'Silence changed',
  'Lift Suspension': 'Suspension lifted',
  'Lift Silence': 'Silence lifted',
  'Restriction Expired': 'Expired',
}
const siteHistory = ref<SiteHistoryItem[]>([]),
  siteHistoryQuery = ref(''),
  siteHistoryCursor = ref(''),
  siteHistoryLoading = ref(false),
  siteHistoryError = ref<unknown>(null)
let siteHistoryLoaded = false
let siteHistoryRequest = 0
function actor(row: HistoryItem) {
  return systemActions.includes(row.action) ? 'System' : `by ${useUser(row.owner).full_name}`
}
async function loadSiteHistory(before = '') {
  const request = ++siteHistoryRequest
  siteHistoryLoading.value = true
  siteHistoryError.value = null
  try {
    const data = await call<Page<SiteHistoryItem>>(
      'gameplan.restriction_queries.restriction_history',
      { query: siteHistoryQuery.value, before },
    )
    if (request !== siteHistoryRequest) return
    siteHistory.value = before ? [...siteHistory.value, ...data.items] : data.items
    siteHistoryCursor.value = data.next_cursor
    siteHistoryLoaded = true
  } catch (e) {
    if (request === siteHistoryRequest) siteHistoryError.value = e
  } finally {
    if (request === siteHistoryRequest) siteHistoryLoading.value = false
  }
}
watch(tab, (value) => {
  if (value === 'history' && !siteHistoryLoaded) loadSiteHistory()
})
watch(siteHistoryQuery, () => loadSiteHistory())
async function showHistory(user: { user: string }) {
  historyUser.value = user.user
  history.value = []
  historyCursor.value = ''
  historyOpen.value = true
  await loadHistory()
}
const historyLoading = ref(false)
// Shown inside the dialog: the page's own error line is hidden behind it.
const historyError = ref<unknown>(null)
async function loadHistory(before = '') {
  historyLoading.value = true
  historyError.value = null
  try {
    const data = await call<Page<HistoryItem>>('gameplan.restriction_queries.account_history', {
      user: historyUser.value,
      before,
    })
    history.value = before ? [...history.value, ...data.items] : data.items
    historyCursor.value = data.next_cursor
  } catch (e) {
    historyError.value = e
  } finally {
    historyLoading.value = false
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
