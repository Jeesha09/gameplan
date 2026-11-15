<template>
  <PageHeaderMobile class="sm:hidden" :title="conversationId ? title : 'Messages'">
    <template v-if="conversationId" #prefix>
      <PageHeaderBackButton :fallback-route="{ name: 'Messages' }" />
    </template>
    <template v-if="conversationId && title" #default>
      <PageHeaderMobileTitle :title="title">
        <template v-if="people[0]" #prefix>
          <ConversationAvatar :people="people" size="sm" />
        </template>
      </PageHeaderMobileTitle>
    </template>
    <template v-if="conversationOptions.length" #suffix>
      <DropdownMoreOptions
        :options="conversationOptions"
        align="end"
        label="Conversation options"
      />
    </template>
    <template v-else-if="!conversationId && canStartConversation" #suffix>
      <div class="flex items-center">
        <Button
          variant="ghost"
          icon="lucide-check-check"
          label="Mark all as read"
          :disabled="!hasUnread"
          @click="readAll"
        />
        <Button
          variant="ghost"
          icon="lucide-square-pen"
          label="New message"
          @click="showNewMessage = true"
        />
      </div>
    </template>
  </PageHeaderMobile>

  <div v-if="!enabled" class="flex h-full flex-col">
    <PageHeader class="hidden sm:flex">
      <PageHeaderTitle title="Messages" />
    </PageHeader>
    <div class="flex flex-1 flex-col items-center justify-center px-6 text-center">
      <span class="lucide-message-circle-off size-7 text-ink-gray-4" />
      <p class="mt-3 text-base-medium text-ink-gray-8">Messages are off</p>
      <p class="mt-1 max-w-sm text-base text-ink-gray-5">
        {{
          isGuest(sessionUser)
            ? 'Direct messages are not available for guests'
            : 'Turn on direct messages to chat privately with members. While off, nobody can message you'
        }}
      </p>
      <Button
        v-if="!isGuest(sessionUser)"
        class="mt-4"
        variant="solid"
        :loading="turningOn"
        @click="turnOn"
      >
        Turn on
      </Button>
    </div>
  </div>
  <div v-else class="flex h-full min-h-0">
    <div
      class="w-full shrink-0 flex-col sm:w-80 sm:border-r"
      :class="conversationId ? 'hidden sm:flex' : 'flex'"
    >
      <header :class="columnHeaderClass">
        <PageHeaderTitle title="Messages" />
        <div v-if="canStartConversation" class="-mr-2 flex items-center">
          <Tooltip text="Mark all as read">
            <Button
              variant="ghost"
              icon="lucide-check-check"
              label="Mark all as read"
              :disabled="!hasUnread"
              @click="readAll"
            />
          </Tooltip>
          <Tooltip text="New message">
            <Button
              variant="ghost"
              icon="lucide-square-pen"
              label="New message"
              @click="showNewMessage = true"
            />
          </Tooltip>
        </div>
      </header>
      <ConversationList class="flex min-h-0 flex-1" :active="conversationId" />
    </div>
    <div
      class="min-w-0 flex-1 flex-col"
      :class="conversationId && !panelOpen ? 'flex' : 'hidden sm:flex'"
    >
      <template v-if="conversationId && !unavailable">
        <header :class="columnHeaderClass">
          <Dropdown v-if="conversationOptions.length" :options="conversationOptions">
            <template #default="{ open }">
              <button
                type="button"
                class="-ml-1.5 flex min-w-0 items-center gap-2 rounded-5 py-1 pl-1.5 pr-1 transition"
                :class="open ? 'bg-surface-gray-3' : 'hover:bg-surface-gray-2'"
              >
                <ConversationAvatar v-if="people[0]" :people="people" size="md" class="shrink-0" />
                <span class="truncate text-lg font-semibold text-ink-gray-9">{{ title }}</span>
                <span class="lucide-chevron-down size-4 shrink-0 text-ink-gray-5" />
              </button>
            </template>
          </Dropdown>
          <span v-else class="flex min-w-0 items-center gap-2">
            <ConversationAvatar v-if="people[0]" :people="people" size="md" class="shrink-0" />
            <span class="truncate text-lg font-semibold text-ink-gray-9">{{ title }}</span>
          </span>
        </header>
        <MessageThread
          :key="`${conversationId}-${to}-${around ?? ''}`"
          class="min-h-0 flex-1"
          :conversation-id="conversationId"
          :to="to"
          :people="people"
          :title="title"
          :around="around"
        />
      </template>
      <div v-else class="flex flex-1 items-center justify-center text-base text-ink-gray-5">
        {{ unavailable ? 'This conversation is not available' : 'Pick a conversation' }}
      </div>
    </div>
    <ConversationPanel
      v-if="panelOpen && conversation && people[0]"
      v-model:tab="panelTab"
      class="w-full shrink-0 sm:w-80 sm:border-l"
      :conversation="conversation.name"
      :people="people"
      @close="panelOpen = false"
    />
  </div>

  <NewMessageDialog v-model="showNewMessage" />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Button,
  Dropdown,
  PageHeader,
  PageHeaderBackButton,
  PageHeaderMobile,
  PageHeaderMobileTitle,
  PageHeaderTitle,
  Tooltip,
  toast,
  usePageMeta,
  type DropdownOptions,
} from 'frappe-ui'
import DropdownMoreOptions from '@/components/DropdownMoreOptions.vue'
import ConversationAvatar from '@/components/Messages/ConversationAvatar.vue'
import ConversationList from '@/components/Messages/ConversationList.vue'
import ConversationPanel from '@/components/Messages/ConversationPanel.vue'
import MessageThread from '@/components/Messages/MessageThread.vue'
import NewMessageDialog from '@/components/Messages/NewMessageDialog.vue'
import { conversationActions } from '@/components/Messages/conversationActions'
import {
  getConversation,
  inbox,
  markAllRead,
  messagesEnabled,
  setMessagesEnabled,
  unreadConversations,
  type Conversation,
} from '@/data/messages'
import { useSessionUser, useUser } from '@/data/users'
import { isGuest } from '@/utils/permissions'

const props = defineProps<{
  conversationId?: string
}>()

const columnHeaderClass =
  'hidden min-h-12 shrink-0 items-center justify-between border-b bg-surface-base px-5 sm:flex'

const route = useRoute()
const router = useRouter()
const sessionUser = useSessionUser()
const showNewMessage = ref(false)
const enabled = computed(() => messagesEnabled())
const canStartConversation = computed(() => enabled.value && !isGuest(sessionUser))
const fetched = ref<Conversation | null>(null)
const unavailable = ref(false)
const turningOn = ref(false)
const panelOpen = ref(false)
const panelTab = ref<'files' | 'links'>('files')

const to = computed(() => route.query.to?.toString() || '')
const around = computed(() => Number(route.query.message) || undefined)
const conversation = computed(
  () => inbox.conversations.find((item) => item.name === props.conversationId) ?? fetched.value,
)
const people = computed(() => (to.value ? [to.value] : (conversation.value?.people ?? [])))
const title = computed(() => people.value.map((user) => useUser(user).full_name).join(', '))
const profileRoute = computed(() => {
  const profile = people.value.length === 1 ? useUser(people.value[0]).user_profile : null
  return profile ? { name: 'PersonProfileProfile', params: { personId: profile } } : undefined
})
const hasUnread = computed(
  () => unreadConversations.value > 0 || inbox.conversations.some((row) => row.unread_count),
)

const conversationOptions = computed<DropdownOptions>(() => {
  const row = conversation.value
  if (!enabled.value || !row || row.name !== props.conversationId) return []
  return [
    {
      group: 'view',
      hideLabel: true,
      options: [
        {
          label: 'View profile',
          icon: 'lucide-user',
          condition: () => Boolean(profileRoute.value),
          onClick: () => profileRoute.value && router.push(profileRoute.value),
        },
        { label: 'Files', icon: 'lucide-files', onClick: () => openPanel('files') },
        { label: 'Links', icon: 'lucide-link', onClick: () => openPanel('links') },
      ],
    },
    { group: 'manage', hideLabel: true, options: conversationActions(row, router) },
  ]
})

function openPanel(tab: 'files' | 'links') {
  panelTab.value = tab
  panelOpen.value = true
}

async function readAll() {
  try {
    await markAllRead()
  } catch {
    toast.error('Could not mark your messages as read')
  }
}

async function turnOn() {
  turningOn.value = true
  try {
    await setMessagesEnabled(true)
  } catch {
    toast.error('Could not turn on direct messages')
  } finally {
    turningOn.value = false
  }
}

watch(
  () => [props.conversationId, enabled.value] as const,
  async ([id, isEnabled]) => {
    unavailable.value = false
    panelOpen.value = false
    fetched.value = null
    if (!id || id === 'new' || !isEnabled) return
    try {
      const row = await getConversation(id)
      if (id === props.conversationId) fetched.value = row
    } catch {
      if (id === props.conversationId) unavailable.value = true
    }
  },
  { immediate: true },
)

usePageMeta(() => ({ title: title.value || 'Messages' }))
</script>
