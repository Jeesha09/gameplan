<template>
  <!-- No `title` prop: the header carries controls, so the panel keeps its own
       heading and hides it on phones, where the page header names the tab. -->
  <PanelHeader>
    <!-- pb-3 keeps the 0.75rem gap to the column header, which now lives at the
         top of the scroll viewport (sticky) instead of inside this fixed region. -->
    <div class="pb-3">
      <div class="flex flex-col gap-4">
        <h2 class="text-md-semibold text-ink-gray-8 max-sm:hidden">Users</h2>
        <div class="flex items-center justify-between gap-3">
          <TextInput
            class="min-w-0 flex-1 md:w-72 md:flex-none"
            placeholder="Search by name or email"
            v-model="search"
            :debounce="300"
          >
            <template #prefix>
              <span class="lucide-search h-4 w-4 text-ink-gray-4" />
            </template>
          </TextInput>
          <Button icon-left="lucide-plus" @click="showInviteDialog = true">Invite</Button>
        </div>
      </div>

      <button
        v-if="pendingInvites.data?.length"
        class="mt-2 flex w-full items-center justify-between gap-3 rounded-4 bg-surface-gray-2 px-3 py-2 text-left transition-colors hover:bg-surface-gray-3"
        @click="showInviteDialog = true"
      >
        <span class="flex items-center gap-2 text-base text-ink-gray-7">
          <span class="lucide-mail h-4 w-4 text-ink-gray-5" />
          {{ pendingInvitesLabel }}
        </span>
        <span class="text-base text-ink-gray-6">View</span>
      </button>
    </div>
  </PanelHeader>

  <PanelBody>
    <!-- Phones: name and email, the role picker, the action; the "user since" column and
         the column header go, the same way CommunityMembersList does it. -->
    <List
      :columns="{
        base: ['minmax(0,1fr)', 'auto', '2rem'],
        md: ['minmax(0,1fr)', '12.5rem', '7.5rem', '2rem'],
      }"
      :row-height="60"
    >
      <!-- Sticky at the viewport top — it rests exactly where it pins, so it
           never visibly moves; the bg covers rows scrolling beneath it. -->
      <ListHeader class="sticky top-0 z-10 bg-surface-elevation-1 max-md:hidden">
        <ListHeaderCellSort :direction="directionFor('name')" @click="toggleSort('name')">
          User
          <template #sort-indicator="{ direction }">
            <span class="size-3.5 text-ink-gray-5" :class="sortIcon(direction)" />
          </template>
        </ListHeaderCellSort>
        <ListHeaderCellSort :direction="directionFor('role')" @click="toggleSort('role')">
          Role
          <template #sort-indicator="{ direction }">
            <span class="size-3.5 text-ink-gray-5" :class="sortIcon(direction)" />
          </template>
        </ListHeaderCellSort>
        <ListHeaderCellSort :direction="directionFor('creation')" @click="toggleSort('creation')">
          User since
          <template #sort-indicator="{ direction }">
            <span class="size-3.5 text-ink-gray-5" :class="sortIcon(direction)" />
          </template>
        </ListHeaderCellSort>
        <ListHeaderCell />
      </ListHeader>

      <!-- Virtualized: only the rows in/near the viewport mount, so a large team
           never instantiates hundreds of role Selects at once. -->
      <ListRows :items="filteredUsers" virtual v-slot="{ item: user }">
        <ListRow>
          <ListCell>
            <UserAvatar :user="user.name" size="xl" />
            <div class="ml-3 min-w-0">
              <div class="truncate text-base text-ink-gray-8">
                {{ user.full_name }}
              </div>
              <div class="mt-1 truncate text-base text-ink-gray-6">
                {{ user.email }}
              </div>
            </div>
          </ListCell>
          <ListCell>
            <Select
              placeholder="Role"
              :options="roleOptions"
              :model-value="user.role"
              @update:model-value="(role) => onRoleChange(user, role)"
            />
          </ListCell>
          <ListCell class="text-base text-ink-gray-6 max-md:hidden">
            <span v-if="user.creation">{{ getMemberSince(user) }}</span>
          </ListCell>
          <ListCell class="justify-end">
            <Button
              variant="ghost"
              icon="lucide-trash-2"
              :label="`Disable ${user.full_name}`"
              @click="disableUser(user)"
            />
          </ListCell>
        </ListRow>
      </ListRows>
    </List>
    <div class="p-3" v-if="hasMoreUsers">
      <Button @click="loadUsers(false)" :loading="loadingUsers">Load more</Button>
    </div>
  </PanelBody>

  <Dialog v-model:open="showInviteDialog">
    <InvitePeople />
  </Dialog>
</template>
<script setup lang="ts">
// Declared so the parent's @close-dialog isn't treated as a failed attribute
// fallthrough (this component renders a fragment); it simply isn't emitted here.
defineEmits<{ (e: 'close-dialog'): void }>()
import { computed, ref, watch } from 'vue'
import { Button, Dialog, Select, dialog, dayjsLocal, useCall, useList } from 'frappe-ui'
import PanelHeader from './PanelHeader.vue'
import PanelBody from './PanelBody.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import {
  List,
  ListCell,
  ListHeader,
  ListHeaderCell,
  ListHeaderCellSort,
  ListRow,
  ListRows,
} from 'frappe-ui/list'
import InvitePeople from './InvitePeople.vue'
import { loadMemberCount, searchUsers, updateUserInfo, type UserInfo } from '@/data/users'
import { GPInvitation } from '@/types/doctypes'

type SortField = 'name' | 'role' | 'creation'
type SortDirection = 'asc' | 'desc'
type UserRow = UserInfo

const roleOptions = [
  { label: 'Admin', value: 'Gameplan Admin', icon: 'lucide-shield-check' },
  { label: 'User', value: 'Gameplan Member', icon: 'lucide-user' },
  { label: 'Guest', value: 'Gameplan Guest', icon: 'lucide-user-lock' },
]

const search = ref('')
const sortField = ref<SortField>('name')
const sortDirection = ref<SortDirection>('asc')
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

// Invites are sent/revoked inside the dialog, so refresh the count on close.
watch(showInviteDialog, (open, wasOpen) => {
  if (wasOpen && !open) {
    pendingInvites.reload()
    loadUsers()
  }
})

// `users` is a useCall resource (no setData); refetch after mutations so the
// list — role labels and membership — reflects the server-side change.
const changeUserRoleCall = useCall<UserInfo, { user: string; role: string }>({
  url: '/api/v2/method/gameplan.api.change_user_role',
  method: 'POST',
  immediate: false,
  onSuccess: updateUserInfo,
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

const PAGE_SIZE = 100
const filteredUsers = ref<UserInfo[]>([])
const hasMoreUsers = ref(false)
const loadingUsers = ref(false)
let usersRequest = 0

async function loadUsers(reset = true) {
  const current = ++usersRequest
  loadingUsers.value = true
  try {
    const page = await searchUsers({
      query: search.value,
      start: reset ? 0 : filteredUsers.value.length,
      limit: PAGE_SIZE,
      order_by: sortField.value === 'name' ? 'full_name' : sortField.value,
      descending: (sortDirection.value === 'desc') !== (sortField.value === 'role'),
    })
    if (current !== usersRequest) return
    filteredUsers.value = reset ? page : [...filteredUsers.value, ...page]
    hasMoreUsers.value = page.length === PAGE_SIZE
  } finally {
    if (current === usersRequest) loadingUsers.value = false
  }
}

watch([search, sortField, sortDirection], () => loadUsers(), { immediate: true })

function toggleSort(field: SortField) {
  if (sortField.value === field) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
    return
  }

  sortField.value = field
  sortDirection.value = defaultSortDirection(field)
}

function directionFor(field: SortField) {
  return sortField.value === field ? sortDirection.value : null
}

function defaultSortDirection(field: SortField): SortDirection {
  return field === 'creation' ? 'desc' : 'asc'
}

function sortIcon(direction: SortDirection | null) {
  if (!direction) return 'lucide-arrow-up-down'
  return direction === 'asc' ? 'lucide-arrow-up' : 'lucide-arrow-down'
}

function getMemberSince(user: UserRow) {
  return dayjsLocal(user.creation).format('MMM YYYY')
}

function changeUserRole(user: UserRow, role: string) {
  dialog.confirm({
    title: 'Change Role',
    message: `Are you sure you want to change ${user.full_name}'s role to ${role}?`,
    confirmLabel: 'Change Role',
    onConfirm: () => {
      changeUserRoleCall.submit({ user: user.name, role }).catch(() => {})
    },
  })
}

function onRoleChange(user: UserRow, role: unknown) {
  // Select emits SelectOptionValue | undefined; narrow to the string role id.
  if (typeof role !== 'string') return
  const isValidRole = roleOptions.some((option) => option.value === role)
  if (!isValidRole || role === user.role) return
  changeUserRole(user, role)
}

function disableUser(user: UserRow) {
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
