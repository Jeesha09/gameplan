<template>
  <div class="flex min-h-0 flex-1 flex-col text-ink-gray-9">
    <template v-if="canModerate || siteWide">
      <div class="flex min-h-0 flex-1 flex-col sm:flex-row">
        <Teleport v-if="!isMobileViewport" to="#moderation-sidebar">
          <Sidebar
            :collapsible="false"
            width="14rem"
            aria-label="Moderation sections"
            class="hidden sm:flex"
          >
            <SidebarHeader title="Moderation" :show-logo="false" />
            <div class="p-3"><slot name="sidebar" /></div>
            <ScrollArea class="min-h-0 flex-1" viewport-class="px-2 pt-0.5 pb-10">
              <SidebarLabel>Community moderation</SidebarLabel>
              <div class="mt-0.5 space-y-0.5">
                <SidebarItem
                  v-for="option in sections"
                  :key="option.value"
                  :label="option.label"
                  :icon="option.icon"
                  :active="!siteWide && tab === option.value"
                  @click="selectSection(option.value)"
                />
              </div>
              <slot name="administration" />
            </ScrollArea>
          </Sidebar>
        </Teleport>
        <div class="space-y-3 border-b border-outline-gray-2 p-4 sm:hidden">
          <slot name="sidebar" />
          <Select
            :model-value="siteWide ? '' : tab"
            aria-label="Moderation section"
            :options="sections"
            @update:model-value="selectSection"
          />
          <slot name="administration" />
        </div>
        <ScrollArea class="min-h-0 min-w-0 flex-1" viewport-class="py-5">
          <div class="body-container">
            <slot v-if="siteWide" name="site-wide" />
            <template v-else>
              <p v-if="sectionDescriptions[tab]" class="pb-5 text-p-base text-ink-gray-6">
                {{ sectionDescriptions[tab] }}
              </p>
              <ErrorMessage
                v-if="error"
                class="mt-4"
                :message="extractServerMessage(error) || 'Could not load moderation data'"
              />
              <WatchedWords
                v-if="tab === 'words' && canManageCommunity(community, useSessionUser())"
                :community-id="communityId"
              />
              <template v-if="tab === 'removed'">
                <div class="flex items-center justify-between gap-3 pb-3">
                  <TabButtons
                    v-model="doctype"
                    :options="[
                      { label: 'Discussions', value: 'GP Discussion' },
                      { label: 'Replies', value: 'GP Comment' },
                    ]"
                  />
                </div>
                <div v-if="items.length" class="border-t border-outline-gray-1">
                  <template v-for="item in items" :key="item.name">
                    <ModerationRow>
                      <template #lead>
                        <Avatar
                          :image="useUser(item.owner).user_image"
                          :label="useUser(item.owner).full_name"
                          size="md"
                        />
                      </template>
                      <template #title>{{ item.title }}</template>
                      <template v-if="item.reason" #detail>{{ item.reason }}</template>
                      <template #meta>{{ useUser(item.owner).full_name }}</template>
                      <template #status>
                        <Badge :label="item.spam_removed_at ? 'Spam' : 'Hidden'" />
                      </template>
                      <template #actions>
                        <Button variant="subtle" @click="restore(item)">Restore</Button>
                        <Dropdown
                          align="end"
                          :button="{
                            icon: 'lucide-more-horizontal',
                            variant: 'ghost',
                            label: 'More actions',
                          }"
                          :options="[
                            {
                              label: selected === item.name ? 'Hide preview' : 'Preview original',
                              icon: 'lucide-eye',
                              onClick: () => preview(item),
                            },
                            {
                              label: 'Open discussion',
                              icon: 'lucide-external-link',
                              onClick: () =>
                                router.push({
                                  name: 'Discussion',
                                  params: {
                                    communityId,
                                    spaceId: item.project,
                                    postId: item.discussion,
                                    slug: item.slug,
                                  },
                                }),
                            },
                          ]"
                        />
                      </template>
                    </ModerationRow>
                    <div
                      v-if="selected === item.name"
                      class="mb-3 ml-10 max-h-96 overflow-y-auto rounded-5 bg-surface-gray-1 p-4"
                    >
                      <CommentEditor :value="previewContent" :editable="false" />
                    </div>
                  </template>
                </div>
                <ModerationEmpty
                  v-else-if="!loading"
                  icon="lucide-trash-2"
                  :title="
                    doctype === 'GP Comment' ? 'No removed replies' : 'No removed discussions'
                  "
                  description="Hidden posts and spam removals appear here, ready to restore."
                />
                <ModerationPager
                  :previous="start > 0"
                  :next="hasMore"
                  @previous="start -= 40"
                  @next="start += 40"
                />
              </template>
              <template v-else-if="tab === 'bans'">
                <div class="flex flex-wrap items-center gap-2 pb-3">
                  <Combobox
                    v-model="targetUser"
                    v-model:query="userQuery"
                    :open="userPickerOpen"
                    :loading="userSearchLoading"
                    variant="outline"
                    open-on-click
                    placeholder="Find a member to ban"
                    aria-label="Member"
                    class="w-full max-w-sm"
                    :options="userOptions"
                    :filterable="false"
                    :empty-text="
                      userQuery.trim().length === 1
                        ? 'Type one more character to search.'
                        : 'No eligible members match this search.'
                    "
                    @update:open="setUserPickerOpen"
                  >
                    <template #item-prefix="{ item }">
                      <Avatar :image="item.image" :label="item.label" size="sm" />
                    </template>
                  </Combobox>
                  <template v-if="targetUser">
                    <Button variant="solid" icon-left="lucide-user-x" @click="banUser">Ban</Button>
                    <Button @click="cleanupOpen = true">Remove all posts</Button>
                  </template>
                  <p v-else class="ml-auto text-p-sm text-ink-gray-6">
                    {{
                      bans.length ? `${bans.length}${hasMore ? '+' : ''} active` : 'No active bans'
                    }}
                  </p>
                </div>
                <div v-if="bans.length" class="border-t border-outline-gray-1">
                  <ModerationRow v-for="ban in bans" :key="ban.user">
                    <template #lead>
                      <Avatar
                        :image="useUser(ban.user).user_image"
                        :label="ban.full_name || useUser(ban.user).full_name"
                        size="md"
                      />
                    </template>
                    <template #title>{{ ban.full_name || useUser(ban.user).full_name }}</template>
                    <template v-if="ban.reason" #detail>{{ ban.reason }}</template>
                    <template #meta>{{ untilLabel(ban.expires_at) }}</template>
                    <template #status>
                      <Badge
                        :label="
                          ban.expires_at ? `Ends ${dayjs(ban.expires_at).fromNow()}` : 'Indefinite'
                        "
                      />
                    </template>
                    <template #actions>
                      <Button variant="subtle" @click="editBan(ban, true)">Lift ban</Button>
                      <Dropdown
                        align="end"
                        :button="{
                          icon: 'lucide-more-horizontal',
                          variant: 'ghost',
                          label: 'More actions',
                        }"
                        :options="[
                          {
                            label: 'Change ban',
                            icon: 'lucide-pencil',
                            onClick: () => editBan(ban),
                          },
                          {
                            label: 'Remove all posts',
                            icon: 'lucide-trash-2',
                            onClick: () => {
                              targetUser = ban.user
                              cleanupOpen = true
                            },
                          },
                          {
                            label: 'View history',
                            icon: 'lucide-history',
                            onClick: () =>
                              router.push({
                                query: {
                                  ...route.query,
                                  tab: 'history',
                                  kind: 'user',
                                  target: ban.user,
                                },
                              }),
                          },
                        ]"
                      />
                    </template>
                  </ModerationRow>
                </div>
                <ModerationEmpty
                  v-else-if="!loading"
                  icon="lucide-user-x"
                  title="No one is banned"
                  description="Banned members can still read, but cannot post, react or vote in this Community."
                />
                <ModerationPager
                  :previous="start > 0"
                  :next="hasMore"
                  @previous="start -= 40"
                  @next="start += 40"
                />
              </template>
              <CleanupDialog
                v-if="cleanupOpen"
                v-model:open="cleanupOpen"
                :user="targetUser"
                :label="useUser(targetUser).full_name || targetUser"
                :community="communityId"
              />
              <RestrictionDialog
                v-if="banTarget"
                :key="`${banTarget.user}-${liftingBan}`"
                v-model:open="banDialogOpen"
                :user="banTarget"
                :community="communityId"
                :lifting="liftingBan"
                @saved="banSaved"
              />
              <ApprovalQueue
                v-if="tab === 'approvals'"
                :key="communityId"
                :community-id="communityId"
              >
                <template #actions>
                  <ApprovalSettings
                    v-if="canManageCommunity(community, useSessionUser())"
                    :key="communityId"
                    :community-id="communityId"
                  />
                </template>
              </ApprovalQueue>
              <ReportQueue v-if="tab === 'reports'" :communityId="communityId" />
              <ModerationHistory v-if="tab === 'history'" :communityId="communityId" />
              <p v-if="loading" role="status" class="mt-4 text-base text-ink-gray-5">Loading…</p>
            </template>
          </div>
        </ScrollArea>
      </div>
    </template>
    <p v-else class="text-base text-ink-gray-5">Only Community moderators can open this page.</p>
  </div>
</template>

<script setup lang="ts">
import { Sidebar, SidebarHeader, SidebarItem, SidebarLabel, ScrollArea } from 'frappe-ui'
import { useIsMobile } from '@/utils/useIsMobile'
import CleanupDialog from '@/components/CleanupDialog.vue'
import RestrictionDialog from '@/components/RestrictionDialog.vue'
import { untilLabel, type RestrictionUser } from '@/data/restrictions'
import WatchedWords from '@/components/WatchedWords.vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import ApprovalQueue from '@/components/ApprovalQueue.vue'
import ApprovalSettings from '@/components/ApprovalSettings.vue'
import ReportQueue from '@/components/ReportQueue.vue'
import { useRoute, useRouter } from 'vue-router'
import ModerationHistory from '@/components/ModerationHistory.vue'
import {
  Avatar,
  Badge,
  Button,
  Combobox,
  Dialog,
  Dropdown,
  Select,
  ErrorMessage,
  TabButtons,
  call,
  dayjs,
  dialog,
  useDoctype,
} from 'frappe-ui'
import ModerationEmpty from '@/components/moderation/ModerationEmpty.vue'
import ModerationPager from '@/components/moderation/ModerationPager.vue'
import ModerationRow from '@/components/moderation/ModerationRow.vue'
import CommentEditor from '@/components/editor/CommentEditor.vue'
import { useCommunity } from '@/data/communities'
import { useSessionUser, useUser } from '@/data/users'
import { canModerateCommunity, canManageCommunity } from '@/utils/permissions'
import { reloadDiscussionLists, useDiscussion } from '@/data/discussions'
import { extractServerMessage } from '@/utils'

const isMobileViewport = useIsMobile()
const sections = computed(() => [
  { label: 'Approvals', value: 'approvals', icon: 'lucide-check-check' },
  { label: 'Reports', value: 'reports', icon: 'lucide-flag' },
  { label: 'Removed content', value: 'removed', icon: 'lucide-trash-2' },
  { label: 'Community bans', value: 'bans', icon: 'lucide-user-x' },
  ...(canManageCommunity(community.value, useSessionUser())
    ? [{ label: 'Watched words', value: 'words', icon: 'lucide-text-search' }]
    : []),
  { label: 'History', value: 'history', icon: 'lucide-history' },
])

const props = defineProps<{ communityId: string; siteWide?: boolean }>()
const emit = defineEmits<{ community: [section: string] }>()
function selectSection(section: string) {
  if (props.siteWide) emit('community', section)
  else tab.value = section
}
const community = useCommunity(() => props.communityId)
const canModerate = computed(() => canModerateCommunity(community.value, useSessionUser()))
const route = useRoute()
const router = useRouter()
const tab = computed({
  get: () =>
    ['approvals', 'reports', 'removed', 'bans', 'words', 'history'].includes(
      String(route.query.tab),
    )
      ? String(route.query.tab)
      : 'approvals',
  set: (value) => {
    router.replace({ query: { ...route.query, tab: value } })
  },
})
const doctype = ref('GP Discussion')
const discussionType = useDoctype('GP Discussion')
const commentType = useDoctype('GP Comment')
const targetType = () => (doctype.value === 'GP Discussion' ? discussionType : commentType)
const start = ref(0)
const loading = ref(false)
const error = ref<unknown>(null)
type RemovedItem = {
  discussion: string
  project: string
  slug: string
  name: string
  title: string
  owner: string
  reason: string
  spam_removed_at?: string
}
const items = ref<RemovedItem[]>([])
const bans = ref<RestrictionUser[]>([])
const banTarget = ref<RestrictionUser | null>(null)
const banDialogOpen = ref(false)
const liftingBan = ref(false)
const hasMore = ref(false)
const selected = ref('')
const previewContent = ref('')
const targetUser = ref('')
const cleanupOpen = ref(false)
const sectionDescriptions: Record<string, string> = {
  approvals: 'Posts from new members wait here until a moderator approves them.',
  reports:
    'Content members have flagged. Review each report, or select several to resolve together.',
  removed: 'Hidden posts and spam removals. Restoring brings a post back exactly as it was.',
  bans: 'Banned members keep reading access but cannot participate in this Community.',
  words: 'Words and phrases that block, hold, flag or censor posts in this Community.',
  history: 'Every moderation action in this Community, newest first.',
}
const userQuery = ref('')
const userPickerOpen = ref(false)
const userSearchLoading = ref(false)
const userHasMore = ref(false)
const userCursor = ref('')
const userOptions = ref<{ label: string; value: string; image: string }[]>([])
let userSearchRequest = 0
let userSearchTimer: ReturnType<typeof setTimeout> | undefined
async function loadBanCandidates(query: string, request: number, after = '') {
  userSearchLoading.value = true
  try {
    const result = await call<{
      items: { name: string; full_name: string; user_image: string }[]
      has_more: boolean
      next_cursor: string
    }>('gameplan.moderation.ban_candidates', {
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

watch([userQuery, userPickerOpen, () => props.communityId], ([query, open]) => {
  const request = ++userSearchRequest
  clearTimeout(userSearchTimer)
  userSearchLoading.value = false
  if (!open) return

  const term = query.trim()
  userOptions.value = []
  userHasMore.value = false
  userCursor.value = ''
  if (term.length === 1) return

  userSearchTimer = setTimeout(() => loadBanCandidates(term, request), term ? 250 : 0)
})

function setUserPickerOpen(open: boolean) {
  userPickerOpen.value = open
  if (open) {
    targetUser.value = ''
    userQuery.value = ''
  }
}

function loadMoreBanCandidatesOnScroll(event: Event) {
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
  loadBanCandidates(userQuery.value.trim(), userSearchRequest, userCursor.value)
}

onMounted(() => document.addEventListener('scroll', loadMoreBanCandidatesOnScroll, true))
onBeforeUnmount(() => document.removeEventListener('scroll', loadMoreBanCandidatesOnScroll, true))

let request = 0
async function load() {
  const current = ++request
  items.value = []
  bans.value = []
  selected.value = ''
  error.value = null
  if (!canModerate.value || ['reports', 'approvals', 'history', 'words'].includes(tab.value)) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    if (tab.value === 'removed') {
      const result = await call<{ items: RemovedItem[]; has_more: boolean }>(
        'gameplan.moderation.removed_content',
        { community: props.communityId, doctype: doctype.value, start: start.value },
      )
      if (current !== request) return
      items.value = result.items
      hasMore.value = result.has_more
    } else {
      const result = await call<typeof bans.value>('gameplan.moderation.community_bans', {
        community: props.communityId,
        start: start.value,
      })
      if (current === request) {
        bans.value = result.slice(0, 40)
        hasMore.value = result.length > 40
      }
    }
  } catch (e) {
    if (current === request) error.value = e
  } finally {
    if (current === request) loading.value = false
  }
}
watch([() => props.communityId, doctype, tab], () => {
  start.value = 0
})
watch([() => props.communityId, doctype, tab, start, canModerate], load, { immediate: true })

async function preview(item: RemovedItem) {
  error.value = null
  if (selected.value === item.name) {
    selected.value = ''
    return
  }
  try {
    const content = await targetType().runDocMethod.submit({
      name: item.name,
      method: 'get_hidden_content',
    })
    previewContent.value = content
    selected.value = item.name
  } catch (e) {
    error.value = e
  }
}
function restore(item: RemovedItem) {
  dialog.confirm({
    title: 'Restore content',
    message:
      'Make this content visible again? A reply stays unavailable while its discussion is removed.',
    confirmLabel: 'Restore',
    onConfirm: async () => {
      await targetType().runDocMethod.submit({ name: item.name, method: 'restore' })
      reloadDiscussionLists()
      await useDiscussion(String(item.discussion)).reload()
      await load()
    },
  })
}
function banUser() {
  editBan({ user: targetUser.value, full_name: useUser(targetUser.value).full_name })
}
function editBan(user: RestrictionUser, lifting = false) {
  banTarget.value = user
  liftingBan.value = lifting
  banDialogOpen.value = true
}
async function banSaved() {
  targetUser.value = ''
  banTarget.value = null
  await load()
}
</script>
