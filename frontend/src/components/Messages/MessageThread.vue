<template>
  <div class="relative flex min-h-0 flex-col">
    <ScrollArea
      ref="scrollArea"
      class="min-h-0 flex-1"
      viewport-class="px-3 sm:px-8 [overflow-anchor:none]"
    >
      <div ref="thread" class="@container w-full pb-2 text-ink-gray-8">
        <div v-if="ready && hasMore" ref="olderTrigger" :key="messages[0]?.name" class="h-px" />
        <p v-if="loadingOlder" class="py-2 text-center text-sm text-ink-gray-5">Loading…</p>
        <p v-if="!loading && !visible.length" class="py-10 text-center text-base text-ink-gray-5">
          This is the start of your conversation with {{ title }}
        </p>
        <section v-for="day in days" :key="day.day" class="mt-2">
          <div
            class="sticky top-0 z-10 flex h-8 items-center justify-center bg-surface-base text-sm-medium leading-tighter text-ink-gray-5"
          >
            {{ day.label }}
          </div>
          <div
            v-for="row in day.rows"
            :key="row.message.name"
            :data-message="row.message.name"
            class="flex gap-2"
            :class="[row.grouped ? 'mt-1.5' : 'mt-4', row.mine ? 'justify-end' : 'justify-start']"
          >
            <div v-if="!row.mine" class="w-7 shrink-0">
              <UserAvatar v-if="!row.grouped" :user="row.message.owner" size="lg" />
            </div>
            <MessageBubble
              :message="row.message"
              :mine="row.mine"
              :last="row.last"
              :seen-at="row.message.name === messages.at(-1)?.name ? seenAt : null"
              :highlighted="row.message.name === highlighted"
              @edit="startEditing(row.message)"
              @delete="confirmDelete(row.message)"
              @reply="startReply(row.message)"
              @react="(emoji) => toggleReaction(row.message, emoji)"
              @jump="jumpTo"
              @preview="(url) => (viewing = { message: row.message.name, url })"
            />
          </div>
        </section>
        <p v-if="loadingNewer" class="py-2 text-center text-sm text-ink-gray-5">Loading…</p>
        <div
          v-if="ready && hasNewer"
          ref="newerTrigger"
          :key="messages.at(-1)?.name"
          class="h-px"
        />
      </div>
    </ScrollArea>
    <div
      v-if="hasNewer"
      class="pointer-events-none absolute inset-x-0 bottom-20 flex justify-center"
    >
      <Button class="pointer-events-auto shadow" icon-left="lucide-arrow-down" @click="showLatest">
        Jump to latest
      </Button>
    </div>
    <div ref="footer" class="w-full px-3 pb-3 sm:px-8">
      <p
        v-if="recipientOff"
        class="rounded-5 border border-outline-gray-2 px-3 py-2.5 text-center text-base text-ink-gray-5"
      >
        {{ title }} is not accepting direct messages
      </p>
      <MessageComposer
        v-else-if="canSend"
        placeholder="Type a message..."
        :send="send"
        :editing="editing"
        :replying-to="replyingTo"
        @cancel="editing = null"
        @cancel-reply="replyingTo = null"
      />
    </div>
    <AttachmentViewer
      v-if="viewing"
      :files="viewerFiles"
      :start="viewerStart"
      @close="viewing = null"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useTemplateRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useDocumentVisibility, useIntersectionObserver, useResizeObserver } from '@vueuse/core'
import { Button, ScrollArea, dayjsLocal, dialog, toast } from 'frappe-ui'
import UserAvatar from '@/components/UserAvatar.vue'
import {
  deleteMessage,
  editMessage,
  getMessages,
  markRead,
  react,
  sendMessage,
  type DirectMessage,
} from '@/data/messages'
import { useSessionUser, useUser } from '@/data/users'
import { onSocketEvent, onSocketReconnect, type ReadCursor } from '@/socket'
import { dayLabel } from '@/utils'
import { isGuest } from '@/utils/permissions'
import AttachmentViewer from './AttachmentViewer.vue'
import MessageBubble from './MessageBubble.vue'
import MessageComposer from './MessageComposer.vue'
import { messageFiles, type ViewerFile } from './messageFiles'

const GROUP_WINDOW_MINUTES = 5
const NEAR_BOTTOM_PX = 120
const HIGHLIGHT_MS = 2000

const props = defineProps<{
  conversationId: string
  to: string
  people: string[]
  title: string
  around?: number
}>()

const router = useRouter()
const sessionUser = useSessionUser()
const visibility = useDocumentVisibility()
const scrollArea = useTemplateRef<InstanceType<typeof ScrollArea>>('scrollArea')
const olderTrigger = useTemplateRef<HTMLElement>('olderTrigger')
const newerTrigger = useTemplateRef<HTMLElement>('newerTrigger')
const footer = useTemplateRef<HTMLElement>('footer')
let footerHeight = 0
const thread = useTemplateRef<HTMLElement>('thread')
let threadHeight = 0
let threadCount = 0
const messages = ref<DirectMessage[]>([])
const visible = computed(() => messages.value.filter((message) => !message.deleted_at))
const hasMore = ref(false)
const hasNewer = ref(false)
const loading = ref(true)
const ready = ref(false)
const loadingOlder = ref(false)
const loadingNewer = ref(false)
const highlighted = ref<number | null>(null)
const editing = ref<DirectMessage | null>(null)
const replyingTo = ref<DirectMessage | null>(null)
const viewing = ref<{ message: number; url: string } | null>(null)
const seen = ref<ReadCursor[]>([])

const seenAt = computed(() => {
  const newest = visible.value.at(-1)
  if (!newest || hasNewer.value || props.people.length !== 1) return null
  if (newest.owner !== sessionUser.name || newest.deleted_at) return null
  const cursor = seen.value.find((item) => item.user === props.people[0])
  return cursor?.at && cursor.message >= newest.name ? cursor.at : null
})

const viewerFiles = computed<ViewerFile[]>(() =>
  visible.value.flatMap((message) =>
    message.deleted_at
      ? []
      : messageFiles(message.content).map((file) => ({
          ...file,
          owner: message.owner,
          creation: message.creation,
          message: message.name,
        })),
  ),
)
const viewerStart = computed(() =>
  viewerFiles.value.findIndex(
    (file) => file.message === viewing.value?.message && file.url === viewing.value?.url,
  ),
)

const viewport = computed(() => scrollArea.value?.viewportElement ?? null)
const isNew = computed(() => props.conversationId === 'new')
const canSend = computed(() => !isGuest(sessionUser) && (!isNew.value || Boolean(props.to)))
const recipient = computed(() => (props.people.length === 1 ? props.people[0] : props.to))
const recipientOff = computed(
  () => Boolean(recipient.value) && useUser(recipient.value).direct_messages_enabled === 0,
)

function groupedWith(message?: DirectMessage, previous?: DirectMessage) {
  if (!message || !previous || previous.owner !== message.owner) return false
  if (message.deleted_at || previous.deleted_at) return false
  const at = dayjsLocal(message.creation)
  const previousAt = dayjsLocal(previous.creation)
  return previousAt.isSame(at, 'day') && at.diff(previousAt, 'minute') < GROUP_WINDOW_MINUTES
}

const days = computed(() => {
  const groups: { day: string; label: string; rows: ReturnType<typeof toRow>[] }[] = []
  visible.value.forEach((message, index) => {
    const row = toRow(message, index)
    const day = row.at.format('YYYY-MM-DD')
    const last = groups[groups.length - 1]
    if (last && last.day === day) last.rows.push(row)
    else groups.push({ day, label: dayLabel(row.at), rows: [row] })
  })
  return groups
})

function sameMinute(message?: DirectMessage, other?: DirectMessage) {
  return Boolean(
    message && other && dayjsLocal(message.creation).isSame(dayjsLocal(other.creation), 'minute'),
  )
}

function toRow(message: DirectMessage, index: number) {
  const next = visible.value[index + 1]
  return {
    message,
    at: dayjsLocal(message.creation),
    mine: message.owner === sessionUser.name,
    grouped: groupedWith(message, visible.value[index - 1]),
    last: !groupedWith(next, message) || !sameMinute(next, message),
  }
}

function scrollToBottom() {
  const element = viewport.value
  if (element) element.scrollTop = element.scrollHeight
}

function isNearBottom() {
  const element = viewport.value
  if (!element) return true
  return element.scrollHeight - element.scrollTop - element.clientHeight < NEAR_BOTTOM_PX
}

function focusMessage(name: number) {
  const element = viewport.value?.querySelector(`[data-message="${name}"]`)
  if (!element) return scrollToBottom()
  element.scrollIntoView({ block: 'center' })
  highlighted.value = name
  setTimeout(() => {
    if (highlighted.value === name) highlighted.value = null
  }, HIGHLIGHT_MS)
}

async function load() {
  if (isNew.value) {
    loading.value = false
    return
  }
  ready.value = false
  const page = await getMessages(props.conversationId, props.around ? { around: props.around } : {})
  messages.value = page.messages
  hasMore.value = page.has_more
  hasNewer.value = page.has_newer
  seen.value = page.seen
  loading.value = false
  await nextTick()
  if (props.around) focusMessage(props.around)
  else scrollToBottom()
  ready.value = true
  readIfVisible()
}

async function loadOlder() {
  const first = messages.value[0]
  if (loadingOlder.value || !hasMore.value || !first) return
  loadingOlder.value = true
  try {
    const page = await getMessages(props.conversationId, { before: first.name })
    const element = viewport.value
    const fromBottom = element ? element.scrollHeight - element.scrollTop : 0
    messages.value = [...page.messages, ...messages.value]
    hasMore.value = page.has_more
    await nextTick()
    if (element) element.scrollTop = element.scrollHeight - fromBottom
  } finally {
    loadingOlder.value = false
  }
}

async function loadNewer() {
  const last = messages.value.at(-1)
  if (loadingNewer.value || !hasNewer.value || !last) return
  loadingNewer.value = true
  try {
    const page = await getMessages(props.conversationId, { after: last.name })
    const known = new Set(messages.value.map((item) => item.name))
    messages.value = [...messages.value, ...page.messages.filter((item) => !known.has(item.name))]
    hasNewer.value = page.has_newer
    seen.value = page.seen
  } finally {
    loadingNewer.value = false
  }
}

async function addMessage(message: DirectMessage) {
  if (hasNewer.value || messages.value.some((item) => item.name === message.name)) return
  const follow = message.owner === sessionUser.name || isNearBottom()
  messages.value = [...messages.value, message]
  await nextTick()
  if (follow) scrollToBottom()
}

function replaceMessage(message: DirectMessage) {
  messages.value = messages.value.map((item) => (item.name === message.name ? message : item))
}

function readIfVisible() {
  if (!isNew.value && visibility.value === 'visible') markRead(props.conversationId)
}

function showLatest() {
  router.replace({ name: 'Conversation', params: { conversationId: props.conversationId } })
}

async function send(content: string) {
  if (editing.value) {
    replaceMessage(await editMessage(editing.value.name, content))
    editing.value = null
    return
  }
  const target = isNew.value ? { to: props.to } : { conversation: props.conversationId }
  const result = await sendMessage(content, target, replyingTo.value?.name)
  replyingTo.value = null
  if (isNew.value || hasNewer.value) {
    router.replace({ name: 'Conversation', params: { conversationId: result.conversation } })
    return
  }
  addMessage(result.message)
}

function startEditing(message: DirectMessage) {
  replyingTo.value = null
  editing.value = message
}

function startReply(message: DirectMessage) {
  editing.value = null
  replyingTo.value = message
}

async function toggleReaction(message: DirectMessage, emoji: string) {
  try {
    replaceMessage(await react(message.name, emoji))
  } catch {
    toast.error('Could not add your reaction')
  }
}

function jumpTo(name: number) {
  if (messages.value.some((item) => item.name === name)) return focusMessage(name)
  router.replace({
    name: 'Conversation',
    params: { conversationId: props.conversationId },
    query: { message: name },
  })
}

function confirmDelete(message: DirectMessage) {
  dialog.danger({
    title: 'Delete message',
    message: 'This removes the message for everyone in this conversation. You cannot undo this.',
    confirmLabel: 'Delete',
    onConfirm: async () => {
      replaceMessage(await deleteMessage(message.name))
      if (editing.value?.name === message.name) editing.value = null
      if (replyingTo.value?.name === message.name) replyingTo.value = null
    },
  })
}

useIntersectionObserver(
  olderTrigger,
  ([entry]) => {
    if (entry?.isIntersecting) loadOlder()
  },
  { root: viewport },
)

useIntersectionObserver(
  newerTrigger,
  ([entry]) => {
    if (entry?.isIntersecting) loadNewer()
  },
  { root: viewport },
)

useResizeObserver(footer, ([entry]) => {
  const height = (entry?.target as HTMLElement | undefined)?.offsetHeight ?? 0
  const grew = height - footerHeight
  footerHeight = height
  const element = viewport.value
  if (!element || grew <= 0) return
  const fromBottom = element.scrollHeight - element.scrollTop - element.clientHeight
  if (fromBottom - grew < NEAR_BOTTOM_PX) scrollToBottom()
})

useResizeObserver(thread, () => {
  const element = viewport.value
  if (!element) return
  const height = element.scrollHeight
  const grew = height - threadHeight
  const sameMessages = messages.value.length === threadCount
  threadHeight = height
  threadCount = messages.value.length
  if (!ready.value || !sameMessages || grew <= 0) return
  const fromBottom = height - element.scrollTop - element.clientHeight
  if (fromBottom - grew < NEAR_BOTTOM_PX) scrollToBottom()
})

watch(visibility, (state) => {
  if (state === 'visible') readIfVisible()
})

const stopReceiving = onSocketEvent('gameplan:message_received', ({ conversation, message }) => {
  if (conversation !== props.conversationId) return
  addMessage(message)
  if (message.owner !== sessionUser.name) readIfVisible()
})
const stopUpdating = onSocketEvent('gameplan:message_updated', ({ conversation, message }) => {
  if (conversation === props.conversationId) replaceMessage(message)
})
const stopSeeing = onSocketEvent('gameplan:messages_seen', ({ conversation, ...cursor }) => {
  if (conversation !== props.conversationId) return
  const known = seen.value.find((item) => item.user === cursor.user)
  if (known && known.message > cursor.message) return
  seen.value = [...seen.value.filter((item) => item.user !== cursor.user), cursor]
})
const stopReconnecting = onSocketReconnect(load)

onMounted(load)
onBeforeUnmount(() => {
  stopReceiving()
  stopUpdating()
  stopSeeing()
  stopReconnecting()
})
</script>
