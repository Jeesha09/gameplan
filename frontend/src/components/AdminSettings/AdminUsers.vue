<template>
  <div class="flex items-center justify-between gap-2">
    <TextInput
      v-model="search"
      class="hidden sm:block"
      type="text"
      placeholder="Search"
      :debounce="500"
    >
      <template #prefix><span class="lucide-search w-4 text-ink-gray-5" /></template>
    </TextInput>
    <div class="ml-auto flex items-center gap-2">
      <Select
        v-if="levelsEnabled"
        v-model="levelFilter"
        class="shrink-0 !w-fit"
        align="end"
        aria-label="Trust level"
        :options="levelFilters"
      />
      <Button
        class="hidden sm:inline-flex"
        variant="solid"
        icon-left="lucide-user-plus-2"
        @click="showInviteDialog = true"
      >
        Invite
      </Button>
    </div>
  </div>
  <div class="mt-4 sm:hidden">
    <TextInput v-model="search" class="w-full" type="text" placeholder="Search" :debounce="500">
      <template #prefix><span class="lucide-search w-4 text-ink-gray-5" /></template>
    </TextInput>
  </div>
  <button
    v-if="pendingInvites.data?.length"
    class="mt-4 flex w-full items-center justify-between gap-3 rounded-4 bg-surface-gray-2 px-3 py-2 text-left transition-colors hover:bg-surface-gray-3"
    @click="showInviteDialog = true"
  >
    <span class="flex items-center gap-2 text-base text-ink-gray-7">
      <span class="lucide-mail h-4 w-4 text-ink-gray-5" />
      {{ pendingInvitesLabel }}
    </span>
    <span class="text-base text-ink-gray-6">View</span>
  </button>
  <div class="-mx-3 mt-4">
    <List class="max-sm:hidden list-gap-3 list-row-px-3" :columns="columns" divider="inset">
      <ListHeader>
        <ListHeaderCellSort
          class="col-span-2"
          :direction="directionFor('full_name')"
          @click="sortBy('full_name')"
        >
          User
          <template #sort-indicator><span /></template>
        </ListHeaderCellSort>
        <ListHeaderCellSort :direction="directionFor('role')" @click="sortBy('role')">
          Role
          <template #sort-indicator><span /></template>
        </ListHeaderCellSort>
        <ListHeaderCellSort
          v-if="levelsEnabled"
          :direction="directionFor('trust_level')"
          @click="sortBy('trust_level')"
        >
          Trust level
          <template #sort-indicator><span /></template>
        </ListHeaderCellSort>
        <ListHeaderCellSort :direction="directionFor('creation')" @click="sortBy('creation')">
          User since
          <template #sort-indicator><span /></template>
        </ListHeaderCellSort>
        <ListHeaderCell />
      </ListHeader>
      <ListRow v-for="user in users" :key="user.name" class="h-15">
        <ListCell><UserAvatar :user="user.name" size="2xl" /></ListCell>
        <ListCell>
          <div class="min-w-0 flex-1">
            <div class="truncate text-base-medium text-ink-gray-8">{{ user.full_name }}</div>
            <div class="mt-1.5 truncate text-base text-ink-gray-5">{{ user.email }}</div>
          </div>
        </ListCell>
        <ListCell>
          <Select
            :options="roleOptions"
            :model-value="user.role"
            :aria-label="`Role of ${user.full_name}`"
            @update:model-value="(role) => onRoleChange(user, role)"
          />
        </ListCell>
        <ListCell v-if="levelsEnabled" class="gap-1">
          <template v-if="levels[user.name]">
            <Badge :label="levelLabel(user.name)" />
            <Badge v-if="levels[user.name].locked" label="Locked" />
          </template>
          <span v-else class="text-base text-ink-gray-4">—</span>
        </ListCell>
        <ListCell class="text-base text-ink-gray-5">
          {{ user.creation ? dayjsLocal(user.creation).format('MMM YYYY') : '' }}
        </ListCell>
        <ListCell class="justify-end">
          <Dropdown
            align="end"
            :options="actionsFor(user)"
            :button="{
              icon: 'lucide-more-horizontal',
              variant: 'ghost',
              label: `Actions for ${user.full_name}`,
            }"
          />
        </ListCell>
      </ListRow>
    </List>
    <List
      class="sm:hidden list-gap-3"
      :columns="['2.5rem', 'minmax(0,1fr)', '2rem']"
      divider="inset"
    >
      <ListRow v-for="user in users" :key="user.name" class="py-2">
        <ListCell><UserAvatar :user="user.name" size="2xl" /></ListCell>
        <ListCell>
          <div class="min-w-0 flex-1">
            <div class="truncate text-base-medium text-ink-gray-8">{{ user.full_name }}</div>
            <div class="mt-1.5 truncate text-base text-ink-gray-5">
              {{ roleLabel(user.role)
              }}<template v-if="levelsEnabled && levels[user.name]">
                · {{ levelLabel(user.name) }}</template
              >
            </div>
          </div>
        </ListCell>
        <ListCell class="justify-end">
          <Dropdown
            align="end"
            :options="actionsFor(user, true)"
            :button="{
              icon: 'lucide-more-horizontal',
              variant: 'ghost',
              label: `Actions for ${user.full_name}`,
            }"
          />
        </ListCell>
      </ListRow>
    </List>
    <EmptyStateBox v-if="!loadingUsers && !users.length" class="mx-3 mt-2">
      <span class="lucide-users mb-1 size-7 text-ink-gray-4" aria-hidden="true" />
      {{ search || levelFilter ? 'No one matches' : 'No users yet' }}
    </EmptyStateBox>
    <div v-if="hasMoreUsers" class="p-3">
      <Button :loading="loadingUsers" @click="loadUsers(false)">Load more</Button>
    </div>
  </div>

  <InvitePeople v-model:open="showInviteDialog" />
  <TrustLevelDialog
    v-if="target"
    :key="`${target.user}-${mode}`"
    v-model:open="levelDialogOpen"
    :member="target"
    :mode="mode"
    @saved="refreshLevels"
  />
  <Dialog v-model:open="requirementsOpen" :title="requirementsTitle">
    <p v-if="progress" class="mb-3 text-p-sm text-ink-gray-7">
      {{ levelDescriptions[progress.level] }}
    </p>
    <TrustRequirements v-if="progress" :progress="progress" />
    <p v-else role="status" class="text-p-sm text-ink-gray-5">Loading…</p>
  </Dialog>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  Badge,
  Button,
  Dialog,
  Dropdown,
  Select,
  TextInput,
  call,
  dayjsLocal,
  dialog,
  toast,
  useCall,
  useList,
} from 'frappe-ui'
import {
  List,
  ListCell,
  ListHeader,
  ListHeaderCell,
  ListHeaderCellSort,
  ListRow,
} from 'frappe-ui/list'
import EmptyStateBox from '@/components/EmptyStateBox.vue'
import InvitePeople from '@/components/Settings/InvitePeople.vue'
import TrustLevelDialog from '@/components/TrustLevelDialog.vue'
import TrustRequirements from '@/components/TrustRequirements.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { loadMemberCount, searchUsers, updateUserInfo, type UserInfo } from '@/data/users'
import {
  LEVEL_NAMES,
  levelDescriptions,
  type LevelNumber,
  type LevelProgress,
  type MemberLevel,
} from '@/data/trustLevels'
import { extractServerMessage } from '@/utils'
import { GPInvitation } from '@/types/doctypes'

type StoredLevel = { level: LevelNumber | null; locked: number; pending: number }

const roleOptions = [
  { label: 'Admin', value: 'Gameplan Admin', icon: 'lucide-shield-check' },
  { label: 'User', value: 'Gameplan Member', icon: 'lucide-user' },
  { label: 'Guest', value: 'Gameplan Guest', icon: 'lucide-user-lock' },
]
const levelFilters = [
  { label: 'All levels', value: '' },
  ...LEVEL_NAMES.map((name, index) => ({ label: name, value: String(index) })),
  { label: 'Not worked out', value: 'pending' },
]

const search = ref('')
type SortField = 'full_name' | 'role' | 'creation' | 'trust_level'
const sortField = ref<SortField>('full_name')
const sortDirection = ref<'asc' | 'desc'>('asc')

function sortBy(field: SortField) {
  if (sortField.value === field) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
    return
  }
  sortField.value = field
  sortDirection.value = ['creation', 'trust_level'].includes(field) ? 'desc' : 'asc'
}

function directionFor(field: SortField) {
  return sortField.value === field ? sortDirection.value : null
}
const levelFilter = ref('')
const showInviteDialog = ref(false)

const pendingInvites = useList<GPInvitation>({
  doctype: 'GP Invitation',
  fields: ['name'],
  filters: { status: 'Pending' },
  cacheKey: 'pending-invitations',
})
const pendingInvitesLabel = computed(() => {
  const count = pendingInvites.data?.length ?? 0
  return `${count} pending invite${count === 1 ? '' : 's'}`
})
watch(showInviteDialog, (open, wasOpen) => {
  if (wasOpen && !open) {
    pendingInvites.reload()
    loadUsers()
  }
})

const PAGE_SIZE = 100
const users = ref<UserInfo[]>([])
const levels = ref<Record<string, StoredLevel>>({})
const levelsEnabled = ref(false)
const hasMoreUsers = ref(false)
const loadingUsers = ref(false)
let usersRequest = 0

const columns = computed(() =>
  levelsEnabled.value
    ? ['2.5rem', 'minmax(8rem,1fr)', '8.5rem', '8.5rem', '6.25rem', '2rem']
    : ['2.5rem', 'minmax(8rem,1fr)', '8.5rem', '6.25rem', '2rem'],
)

async function loadUsers(reset = true) {
  const current = ++usersRequest
  loadingUsers.value = true
  try {
    const page = await searchUsers({
      query: search.value,
      start: reset ? 0 : users.value.length,
      limit: PAGE_SIZE,
      order_by: sortField.value,
      descending: sortDirection.value === 'desc',
      ...(levelFilter.value ? { trust_level: levelFilter.value } : {}),
    })
    const result = await fetchLevels(page.map((user) => user.name))
    if (current !== usersRequest) return
    users.value = reset ? page : [...users.value, ...page]
    levels.value = reset ? result.levels : { ...levels.value, ...result.levels }
    levelsEnabled.value = Boolean(result.enabled)
    if (!levelsEnabled.value) levelFilter.value = ''
    hasMoreUsers.value = page.length === PAGE_SIZE
  } catch (error) {
    if (current === usersRequest) toast.error(extractServerMessage(error) || 'Could not load users')
  } finally {
    if (current === usersRequest) loadingUsers.value = false
  }
}

function fetchLevels(names: string[]) {
  return call<{ enabled: number; levels: Record<string, StoredLevel> }>(
    'gameplan.trust_levels.user_levels',
    { users: names },
  )
}

async function refreshLevels() {
  const result = await fetchLevels(users.value.map((user) => user.name))
  levels.value = result.levels
}

watch([search, sortField, sortDirection, levelFilter], () => loadUsers(), { immediate: true })

function levelLabel(user: string) {
  const stored = levels.value[user]
  if (!stored || stored.level === null) return 'Not worked out'
  return LEVEL_NAMES[stored.level]
}

function roleLabel(role?: string) {
  return roleOptions.find((option) => option.value === role)?.label || ''
}

const target = ref<MemberLevel | null>(null)
const mode = ref<'level' | 'lock'>('level')
const levelDialogOpen = ref(false)
const requirementsOpen = ref(false)
const requirementsTitle = ref('')
const progress = ref<LevelProgress | null>(null)

function memberLevel(user: UserInfo): MemberLevel {
  const stored = levels.value[user.name]
  return {
    user: user.name,
    full_name: user.full_name,
    level: (stored?.level ?? 0) as LevelNumber,
    locked: stored?.locked ?? 0,
    pending: stored?.pending ?? 1,
  }
}

function openLevelDialog(user: UserInfo, nextMode: 'level' | 'lock') {
  target.value = memberLevel(user)
  mode.value = nextMode
  levelDialogOpen.value = true
}

async function showRequirements(user: UserInfo) {
  requirementsTitle.value = user.full_name || user.name
  progress.value = null
  requirementsOpen.value = true
  try {
    progress.value = await call<LevelProgress>('gameplan.trust_levels.member_progress', {
      user: user.name,
    })
    refreshLevels()
  } catch (error) {
    requirementsOpen.value = false
    toast.error(extractServerMessage(error) || 'Could not load requirements')
  }
}

function actionsFor(user: UserInfo, mobile = false) {
  const stored = levels.value[user.name]
  const trust =
    levelsEnabled.value && stored
      ? [
          {
            label: 'Change trust level',
            icon: 'lucide-award',
            onClick: () => openLevelDialog(user, 'level'),
          },
          {
            label: stored.locked ? 'Unlock trust level' : 'Lock trust level',
            icon: stored.locked ? 'lucide-lock-open' : 'lucide-lock',
            onClick: () => openLevelDialog(user, 'lock'),
          },
          {
            label: 'Show requirements',
            icon: 'lucide-list-checks',
            onClick: () => showRequirements(user),
          },
        ]
      : []
  const roles = mobile
    ? roleOptions
        .filter((option) => option.value !== user.role)
        .map((option) => ({
          label: `Make ${option.label.toLowerCase()}`,
          icon: option.icon,
          onClick: () => onRoleChange(user, option.value),
        }))
    : []
  return [
    ...roles,
    ...trust,
    {
      label: 'Disable',
      icon: 'lucide-trash-2',
      theme: 'red' as const,
      onClick: () => disableUser(user),
    },
  ]
}

const changeUserRoleCall = useCall<UserInfo, { user: string; role: string }>({
  url: '/api/v2/method/gameplan.api.change_user_role',
  method: 'POST',
  immediate: false,
  onSuccess: (user) => {
    updateUserInfo(user)
    refreshLevels()
  },
})
const disableUserCall = useCall<string, { user: string }>({
  url: '/api/v2/method/gameplan.api.disable_user',
  method: 'POST',
  immediate: false,
  onSuccess: () => {
    loadUsers()
    loadMemberCount()
  },
})

function onRoleChange(user: UserInfo, role: unknown) {
  if (typeof role !== 'string' || role === user.role) return
  if (!roleOptions.some((option) => option.value === role)) return
  dialog.confirm({
    title: 'Change Role',
    message: `Are you sure you want to change ${user.full_name}'s role to ${roleLabel(role)}?`,
    confirmLabel: 'Change Role',
    onConfirm: () => {
      changeUserRoleCall.submit({ user: user.name, role }).catch(() => {})
    },
  })
}

function disableUser(user: UserInfo) {
  dialog.danger({
    title: 'Disable user',
    message: `${user.full_name} (${user.email}) will be disabled and can no longer sign in to Gameplan. You can re-enable them later from the Frappe admin.`,
    confirmLabel: 'Disable',
    onConfirm: () => {
      disableUserCall.submit({ user: user.name }).catch(() => {})
    },
  })
}
</script>
