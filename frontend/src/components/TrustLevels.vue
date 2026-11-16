<template>
  <p class="pb-5 text-p-base text-ink-gray-6">
    Every member has one level across the site. Members earn New, Basic, Member and Regular from
    visits, discussions entered, reactions and replies. Change or lock a level by hand.
  </p>
  <div class="flex flex-wrap items-center justify-between gap-3 pb-3">
    <!-- Seven filters are wider than a phone, so the strip scrolls on its own. -->
    <div class="max-w-full overflow-x-auto">
      <TabButtons v-model="filter" :options="filters" />
    </div>
    <div class="flex items-center gap-2">
      <TextInput
        v-model="query"
        class="w-48"
        placeholder="Search by name"
        type="search"
        aria-label="Search by name"
      >
        <template #prefix><span class="lucide-search size-4" aria-hidden="true" /></template>
      </TextInput>
      <TrustLevelSettings @saved="reload" />
    </div>
  </div>
  <ErrorMessage
    v-if="error"
    class="pb-3"
    :message="extractServerMessage(error) || 'Could not load trust levels'"
  />
  <div v-if="phase === 'loading'" class="border-t border-outline-gray-1">
    <ListRowSkeleton
      v-for="index in 6"
      :key="index"
      :show-separator="index < 6"
      label="Loading member"
    />
  </div>
  <ModerationEmpty
    v-else-if="phase === 'off'"
    icon="lucide-award"
    title="Trust levels are off"
    description="Turn them on under Trust level settings."
  />
  <ModerationEmpty
    v-else-if="phase === 'empty'"
    icon="lucide-award"
    :title="query.trim() ? 'No one matches your search' : 'No one at this level'"
    description="Global admins are not listed: they have no level."
  />
  <!-- A new filter or search keeps the current rows on screen until its results arrive, so
       switching tabs does not flash an empty list. -->
  <div
    v-else-if="phase === 'rows'"
    class="border-t border-outline-gray-1 transition-opacity"
    :class="refreshing ? 'opacity-60' : ''"
    :aria-busy="refreshing"
    data-testid="trust-level-list"
  >
    <template v-for="member in members" :key="member.user">
      <ModerationRow>
        <template #lead>
          <Avatar
            :image="useUser(member.user).user_image"
            :label="member.full_name || member.user"
            size="md"
          />
        </template>
        <template #title>{{ member.full_name || member.user }}</template>
        <template #meta>{{ meta(member) }}</template>
        <template #status>
          <Badge :label="member.pending ? 'Not calculated' : LEVEL_NAMES[member.level]" />
          <Badge v-if="member.locked" label="Locked" />
        </template>
        <template #actions>
          <Button variant="subtle" @click="openDialog(member, 'level')">Change</Button>
          <Dropdown
            align="end"
            :button="{ icon: 'lucide-more-horizontal', variant: 'ghost', label: 'More actions' }"
            :options="[
              {
                label: expanded === member.user ? 'Hide requirements' : 'Show requirements',
                icon: 'lucide-list-checks',
                onClick: () => toggle(member),
              },
              {
                label: member.locked ? 'Unlock level' : 'Lock level',
                icon: member.locked ? 'lucide-lock-open' : 'lucide-lock',
                onClick: () => openDialog(member, 'lock'),
              },
            ]"
          />
        </template>
      </ModerationRow>
      <div
        v-if="expanded === member.user"
        class="mb-3 ml-10 rounded-5 bg-surface-gray-1 p-4"
        data-testid="trust-requirements"
      >
        <p class="mb-3 text-p-sm text-ink-gray-7">{{ levelDescriptions[member.level] }}</p>
        <TrustRequirements v-if="progress" :progress="progress" />
        <p v-else role="status" class="text-p-sm text-ink-gray-5">Loading…</p>
      </div>
    </template>
    <ListRowSkeleton v-if="loadingMore" label="Loading more members" />
  </div>
  <!-- Scrolling this marker into view loads the next page. -->
  <div ref="sentinel" aria-hidden="true" class="h-px" />
  <TrustLevelDialog
    v-if="target"
    :key="`${target.user}-${mode}`"
    v-model:open="dialogOpen"
    :member="target"
    :mode="mode"
    @saved="reload"
  />
</template>
<script setup lang="ts">
import { computed, ref, useTemplateRef, watch } from 'vue'
import { useIntersectionObserver } from '@vueuse/core'
import {
  Avatar,
  Badge,
  Button,
  Dropdown,
  ErrorMessage,
  TabButtons,
  TextInput,
  call,
} from 'frappe-ui'
import ListRowSkeleton from '@/components/ListRowSkeleton.vue'
import ModerationEmpty from '@/components/moderation/ModerationEmpty.vue'
import ModerationRow from '@/components/moderation/ModerationRow.vue'
import TrustLevelDialog from '@/components/TrustLevelDialog.vue'
import TrustLevelSettings from '@/components/TrustLevelSettings.vue'
import TrustRequirements from '@/components/TrustRequirements.vue'
import { useUser } from '@/data/users'
import {
  LEVEL_NAMES,
  levelDescriptions,
  type LevelProgress,
  type MemberLevel,
} from '@/data/trustLevels'
import { extractServerMessage } from '@/utils'

type Page = { enabled: number; members: MemberLevel[]; more: boolean }

const filters = [
  { label: 'All', value: '' },
  ...LEVEL_NAMES.map((name, index) => ({ label: name, value: String(index) })),
  { label: 'Not calculated', value: 'pending' },
]
const filter = ref('')
const query = ref('')
const members = ref<MemberLevel[]>([])
const enabled = ref(true)
const more = ref(false)
const loaded = ref(false)
const refreshing = ref(false)
const loadingMore = ref(false)
const error = ref<unknown>(null)
const expanded = ref('')
const progress = ref<LevelProgress | null>(null)
const target = ref<MemberLevel | null>(null)
const mode = ref<'level' | 'lock'>('level')
const dialogOpen = ref(false)

/** What the list area shows. Loaded rows stay on screen while a new filter refetches. */
const phase = computed((): 'loading' | 'off' | 'empty' | 'rows' | 'failed' => {
  if (!loaded.value) return error.value ? 'failed' : 'loading'
  if (!enabled.value) return 'off'
  return members.value.length ? 'rows' : 'empty'
})

function meta(member: MemberLevel) {
  if (member.pending)
    return 'Level not calculated yet. It is calculated the first time it is needed.'
  return member.user
}

function openDialog(member: MemberLevel, nextMode: 'level' | 'lock') {
  target.value = member
  mode.value = nextMode
  dialogOpen.value = true
}

async function toggle(member: MemberLevel) {
  if (expanded.value === member.user) {
    expanded.value = ''
    return
  }
  expanded.value = member.user
  progress.value = null
  try {
    const result = await call<LevelProgress>('gameplan.trust_levels.member_progress', {
      user: member.user,
    })
    if (expanded.value === member.user) progress.value = result
  } catch (e) {
    error.value = e
    expanded.value = ''
  }
}

let request = 0
function fetchPage(after = '') {
  return call<Page>('gameplan.trust_levels.member_levels', {
    level: filter.value,
    query: query.value.trim(),
    after,
  })
}

/** Load the first page for the current filter and search, replacing the list when it arrives. */
async function reload() {
  const current = ++request
  refreshing.value = loaded.value
  loadingMore.value = false
  error.value = null
  try {
    const page = await fetchPage()
    if (current !== request) return
    enabled.value = Boolean(page.enabled)
    members.value = page.members
    more.value = page.more
    expanded.value = ''
    loaded.value = true
  } catch (e) {
    if (current === request) error.value = e
  } finally {
    if (current === request) refreshing.value = false
  }
}

/** Append the page after the last row. A reload in flight wins over it. */
async function loadMore() {
  if (!more.value || loadingMore.value || refreshing.value || !members.value.length) return
  const current = request
  loadingMore.value = true
  try {
    const page = await fetchPage(members.value[members.value.length - 1].user)
    if (current !== request) return
    members.value = [...members.value, ...page.members]
    more.value = page.more
  } catch (e) {
    if (current === request) error.value = e
  } finally {
    if (current === request) loadingMore.value = false
  }
}

const sentinel = useTemplateRef<HTMLElement>('sentinel')
useIntersectionObserver(
  sentinel,
  ([entry]) => {
    if (entry?.isIntersecting) loadMore()
  },
  // Start loading a little before the end comes into view.
  { rootMargin: '0px 0px 400px 0px' },
)
// A page that does not fill the screen leaves the marker in view, so keep loading.
watch(members, () => requestAnimationFrame(checkSentinel), { flush: 'post' })
function checkSentinel() {
  const element = sentinel.value
  if (element && element.getBoundingClientRect().top < window.innerHeight + 400) loadMore()
}

let typing: ReturnType<typeof setTimeout>
watch(query, () => {
  clearTimeout(typing)
  typing = setTimeout(reload, 300)
})
watch(filter, reload, { immediate: true })
</script>
