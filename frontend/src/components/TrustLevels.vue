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
      <TrustLevelSettings @saved="load" />
    </div>
  </div>
  <ErrorMessage
    v-if="error"
    class="pb-3"
    :message="extractServerMessage(error) || 'Could not load trust levels'"
  />
  <ModerationEmpty
    v-if="!loading && !error && !enabled"
    icon="lucide-award"
    title="Trust levels are off"
    description="Turn them on under Trust level settings."
  />
  <template v-else-if="members.length">
    <div class="border-t border-outline-gray-1" data-testid="trust-level-list">
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
            <Badge :label="LEVEL_NAMES[member.level]" />
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
    </div>
  </template>
  <ModerationEmpty
    v-else-if="!loading && !error"
    icon="lucide-award"
    :title="query ? 'No one matches your search' : 'No one at this level'"
    description="Global admins are not listed: they have no level."
  />
  <p v-if="loading" role="status" class="mt-4 text-base text-ink-gray-5">Loading…</p>
  <ModerationPager
    :previous="start > 0"
    :next="more"
    @previous="start -= PAGE"
    @next="start += PAGE"
  />
  <TrustLevelDialog
    v-if="target"
    :key="`${target.user}-${mode}`"
    v-model:open="dialogOpen"
    :member="target"
    :mode="mode"
    @saved="load"
  />
</template>
<script setup lang="ts">
import { ref, watch } from 'vue'
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
import ModerationEmpty from '@/components/moderation/ModerationEmpty.vue'
import ModerationPager from '@/components/moderation/ModerationPager.vue'
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

const PAGE = 50
const filters = [
  { label: 'All', value: '' },
  ...LEVEL_NAMES.map((name, index) => ({ label: name, value: String(index) })),
  { label: 'Not worked out', value: 'pending' },
]
const filter = ref('')
const query = ref('')
const start = ref(0)
const members = ref<MemberLevel[]>([])
const enabled = ref(true)
const more = ref(false)
const loading = ref(false)
const error = ref<unknown>(null)
const expanded = ref('')
const progress = ref<LevelProgress | null>(null)
const target = ref<MemberLevel | null>(null)
const mode = ref<'level' | 'lock'>('level')
const dialogOpen = ref(false)

function meta(member: MemberLevel) {
  if (member.pending) return 'Not worked out yet. It is worked out when first needed.'
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
async function load() {
  const current = ++request
  loading.value = true
  error.value = null
  try {
    const result = await call<{ enabled: number; members: MemberLevel[]; more: boolean }>(
      'gameplan.trust_levels.member_levels',
      { level: filter.value, query: query.value, start: start.value },
    )
    if (current !== request) return
    enabled.value = Boolean(result.enabled)
    members.value = result.members
    more.value = result.more
  } catch (e) {
    if (current === request) error.value = e
  } finally {
    if (current === request) loading.value = false
  }
}
let typing: ReturnType<typeof setTimeout>
watch(query, () => {
  clearTimeout(typing)
  typing = setTimeout(() => {
    start.value = 0
    load()
  }, 300)
})
watch(filter, () => {
  start.value = 0
  expanded.value = ''
})
watch([filter, start], load, { immediate: true })
</script>
