import { reactive, ref, watch } from 'vue'
import { call } from 'frappe-ui'
import type { Router } from 'vue-router'
import { onSocketEvent, onSocketReconnect, type ReadCursor } from '@/socket'
import { isAnonymousVisitor } from '@/utils/publicAccess'
import { onReconnect } from './online'
import { siteSettings } from './siteSettings'
import { useSessionUser, useUser } from './users'

const METHODS = 'gameplan.direct_messages'

export interface DirectMessage {
  name: number
  owner: string
  content: string
  creation: string
  edited_at: string | null
  deleted_at: string | null
  reply_to: number | null
  reply: MessageReply | null
  reactions: Record<string, string[]>
}

interface MessageReply {
  name: number
  owner: string
  snippet: string
  deleted: boolean
}

export interface Conversation {
  name: string
  is_group: 0 | 1
  people: string[]
  last_message: number
  last_message_at: string | null
  last_message_by: string | null
  last_message_preview: string | null
  unread_count: number
  muted: 0 | 1
}

export interface MessageHit {
  name: number
  conversation: string
  owner: string
  creation: string
  snippet: string
  people: string[]
}

interface MessagePage {
  messages: DirectMessage[]
  has_more: boolean
  has_newer: boolean
  seen: ReadCursor[]
}

export type SharedMessage = Pick<DirectMessage, 'name' | 'owner' | 'content' | 'creation'>

export const unreadConversations = ref(0)

export const inbox = reactive({
  conversations: [] as Conversation[],
  hasMore: false,
  loading: false,
  loaded: false,
})

export function messagesEnabled() {
  return siteSettings.direct_messages_enabled && Boolean(useSessionUser().direct_messages_enabled)
}

async function loadUnreadConversations() {
  unreadConversations.value = await call<number>(`${METHODS}.get_unread_conversation_count`)
}

export async function loadConversations(more = false) {
  if (inbox.loading) return
  inbox.loading = true
  try {
    const page = await call<{ conversations: Conversation[]; has_more: boolean }>(
      `${METHODS}.get_conversations`,
      { before: more ? inbox.conversations.at(-1)?.last_message : undefined },
    )
    inbox.conversations = more
      ? [...inbox.conversations, ...page.conversations]
      : page.conversations
    inbox.hasMore = page.has_more
    inbox.loaded = true
  } finally {
    inbox.loading = false
  }
}

export function getConversation(conversation: string) {
  return call<Conversation>(`${METHODS}.get_conversation`, { conversation })
}

export function getMessages(
  conversation: string,
  page: { before?: number; after?: number; around?: number } = {},
) {
  return call<MessagePage>(`${METHODS}.get_messages`, { conversation, ...page })
}

export function sendMessage(
  content: string,
  target: { conversation: string } | { to: string },
  replyTo?: number,
) {
  return call<{ conversation: string; message: DirectMessage }>(`${METHODS}.send_message`, {
    content,
    ...target,
    reply_to: replyTo,
  })
}

export function react(message: number, emoji: string) {
  return call<DirectMessage>(`${METHODS}.react`, { message, emoji })
}

export function editMessage(message: number, content: string) {
  return call<DirectMessage>(`${METHODS}.edit_message`, { message, content })
}

export function deleteMessage(message: number) {
  return call<DirectMessage>(`${METHODS}.delete_message`, { message })
}

export function searchMessages(query: string) {
  return call<{ conversations: Conversation[]; messages: MessageHit[] }>(`${METHODS}.search`, {
    query,
  })
}

export function getSharedMessages(
  conversation: string,
  kind: 'files' | 'links',
  query: string,
  before?: number,
) {
  return call<{ messages: SharedMessage[]; has_more: boolean }>(`${METHODS}.get_shared_messages`, {
    conversation,
    kind,
    query,
    before,
  })
}

export function markRead(conversation: string) {
  const row = inbox.conversations.find((item) => item.name === conversation)
  if (row) row.unread_count = 0
  return call(`${METHODS}.mark_read`, { conversation })
}

export async function markAllRead() {
  const unread = inbox.conversations.filter((row) => row.unread_count)
  unread.forEach((row) => (row.unread_count = 0))
  const previous = unreadConversations.value
  unreadConversations.value = 0
  try {
    await call(`${METHODS}.mark_all_read`)
  } catch (error) {
    unreadConversations.value = previous
    loadConversations()
    throw error
  }
}

export async function clearConversation(conversation: string) {
  unreadConversations.value = await call<number>(`${METHODS}.clear_conversation`, { conversation })
  removeConversation(conversation)
}

function removeConversation(conversation: string) {
  inbox.conversations = inbox.conversations.filter((item) => item.name !== conversation)
}

export async function setMuted(conversation: string, muted: boolean) {
  const row = inbox.conversations.find((item) => item.name === conversation)
  const previous = row?.muted
  if (row) row.muted = muted ? 1 : 0
  try {
    unreadConversations.value = await call<number>(`${METHODS}.set_muted`, { conversation, muted })
  } catch (error) {
    if (row && previous !== undefined) row.muted = previous
    throw error
  }
}

export async function setMessagesEnabled(enabled: boolean) {
  unreadConversations.value = await call<number>(`${METHODS}.set_direct_messages_enabled`, {
    enabled,
  })
  useSessionUser().direct_messages_enabled = enabled ? 1 : 0
  inbox.conversations = []
  inbox.loaded = false
}

export async function setBlocked(user: string, blocked: boolean) {
  await call(`${METHODS}.${blocked ? 'block_user' : 'unblock_user'}`, { user })
  useUser(user).blocked = blocked ? 1 : 0
}

export function getBlockedUsers() {
  return call<string[]>(`${METHODS}.get_blocked_users`)
}

export async function openDirectMessage(router: Router, user: string) {
  const conversation = await call<string | null>(`${METHODS}.get_direct_conversation`, { user })
  return router.push(
    conversation
      ? { name: 'Conversation', params: { conversationId: conversation } }
      : { name: 'Conversation', params: { conversationId: 'new' }, query: { to: user } },
  )
}

async function refreshConversation(conversation: string) {
  const row = await getConversation(conversation)
  inbox.conversations = [
    row,
    ...inbox.conversations.filter((item) => item.name !== conversation),
  ].sort((first, second) => second.last_message - first.last_message)
}

onSocketEvent('gameplan:message_received', ({ conversation, unread_conversations }) => {
  unreadConversations.value = unread_conversations
  if (inbox.loaded) refreshConversation(conversation)
})

onSocketEvent('gameplan:message_updated', ({ conversation, message }) => {
  const row = inbox.conversations.find((item) => item.name === conversation)
  if (row?.last_message === message.name) refreshConversation(conversation)
})

onSocketEvent('gameplan:messages_read', ({ conversation, unread_conversations }) => {
  unreadConversations.value = unread_conversations
  for (const row of inbox.conversations) {
    if (conversation === null || row.name === conversation) row.unread_count = 0
  }
})

onSocketEvent('gameplan:conversation_cleared', ({ conversation, unread_conversations }) => {
  unreadConversations.value = unread_conversations
  removeConversation(conversation)
})

onSocketEvent('gameplan:conversation_muted', ({ conversation, muted, unread_conversations }) => {
  unreadConversations.value = unread_conversations
  const row = inbox.conversations.find((item) => item.name === conversation)
  if (row) row.muted = muted
})

function reload() {
  if (isAnonymousVisitor() || !messagesEnabled()) return
  loadUnreadConversations()
  if (inbox.loaded) loadConversations()
}

onSocketReconnect(reload)
onReconnect(reload)
watch(
  messagesEnabled,
  (enabled) => {
    if (enabled) reload()
    else unreadConversations.value = 0
  },
  { immediate: true },
)
