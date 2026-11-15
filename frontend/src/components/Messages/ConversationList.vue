<template>
  <div class="min-h-0 flex-col">
    <div class="shrink-0 px-2 pt-2">
      <TextInput v-model="query" class="w-full" placeholder="Search messages" :debounce="300">
        <template #prefix>
          <span class="lucide-search h-4 w-4 text-ink-gray-4" />
        </template>
      </TextInput>
    </div>
    <ScrollArea class="min-h-0 flex-1" viewport-class="p-2">
      <template v-if="searching">
        <template v-if="!results.loaded">
          <ListRowSkeleton v-for="index in 4" :key="index" label="Searching" />
        </template>
        <p v-else-if="!hasResults" class="px-4 py-10 text-center text-base text-ink-gray-5">
          No results
        </p>
        <template v-else>
          <section v-if="results.conversations.length">
            <h3 :class="groupLabelClass">People</h3>
            <ConversationRow
              v-for="row in results.conversations"
              :key="row.name"
              :row="row"
              :active="row.name === active"
            />
          </section>
          <section v-if="results.messages.length" class="mt-2">
            <h3 :class="groupLabelClass">Messages</h3>
            <router-link
              v-for="hit in results.messages"
              :key="hit.name"
              :to="{
                name: 'Conversation',
                params: { conversationId: hit.conversation },
                query: { message: hit.name },
              }"
              class="flex items-center gap-3 rounded-5 px-2.5 py-2 transition hover:bg-surface-gray-2"
            >
              <UserAvatar v-if="hit.people[0]" :user="hit.people[0]" size="xl" class="shrink-0" />
              <div class="min-w-0 flex-1">
                <div class="flex items-baseline justify-between gap-2">
                  <span class="truncate text-base text-ink-gray-8">
                    {{ hit.people.map((user) => useUser(user).full_name).join(', ') }}
                  </span>
                  <span class="shrink-0 text-sm text-ink-gray-5">
                    {{ relativeTimestamp(hit.creation) }}
                  </span>
                </div>
                <p class="mt-0.5 line-clamp-2 text-sm text-ink-gray-5">
                  <template v-if="hit.owner === sessionUser.name">You: </template>
                  <template v-for="(part, index) in highlight(hit.snippet)" :key="index">
                    <span v-if="part.match" class="text-sm-medium text-ink-gray-8">
                      {{ part.text }}
                    </span>
                    <template v-else>{{ part.text }}</template>
                  </template>
                </p>
              </div>
            </router-link>
          </section>
        </template>
      </template>
      <template v-else>
        <template v-if="!inbox.loaded">
          <ListRowSkeleton v-for="index in 6" :key="index" label="Loading conversation" />
        </template>
        <p
          v-else-if="!inbox.conversations.length"
          class="px-4 py-10 text-center text-base text-ink-gray-5"
        >
          No messages yet
        </p>
        <template v-else>
          <ConversationRow
            v-for="row in inbox.conversations"
            :key="row.name"
            :row="row"
            :active="row.name === active"
          />
          <div v-if="inbox.hasMore" class="mt-2 flex justify-center">
            <Button variant="ghost" :loading="inbox.loading" @click="loadConversations(true)">
              Load more
            </Button>
          </div>
        </template>
      </template>
    </ScrollArea>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Button, ScrollArea, TextInput } from 'frappe-ui'
import ListRowSkeleton from '@/components/ListRowSkeleton.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import {
  inbox,
  loadConversations,
  searchMessages,
  type Conversation,
  type MessageHit,
} from '@/data/messages'
import { useSessionUser, useUser } from '@/data/users'
import { relativeTimestamp } from '@/utils'
import ConversationRow from './ConversationRow.vue'

const MIN_QUERY_LENGTH = 1

defineProps<{
  active?: string
}>()

const groupLabelClass =
  'flex h-8 items-center px-2.5 text-sm-medium leading-tighter text-ink-gray-5'

const sessionUser = useSessionUser()
const query = ref('')
const results = reactive({
  conversations: [] as Conversation[],
  messages: [] as MessageHit[],
  loaded: false,
})
let request = 0

const trimmed = computed(() => query.value.trim())
const searching = computed(() => trimmed.value.length >= MIN_QUERY_LENGTH)
const hasResults = computed(() => results.conversations.length || results.messages.length)

watch(trimmed, async (value) => {
  const current = ++request
  results.loaded = false
  if (value.length < MIN_QUERY_LENGTH) return
  try {
    const found = await searchMessages(value)
    if (current !== request) return
    results.conversations = found.conversations
    results.messages = found.messages
  } catch {
    if (current !== request) return
    results.conversations = []
    results.messages = []
  }
  results.loaded = true
})

const wordStart = computed(() => {
  const escaped = trimmed.value.replace(/\s+/g, ' ').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`(?<![\\p{L}\\p{N}_])${escaped}`, 'giu')
})

function highlight(text: string) {
  const parts: { text: string; match: boolean }[] = []
  let start = 0
  for (const found of text.matchAll(wordStart.value)) {
    if (found.index > start) parts.push({ text: text.slice(start, found.index), match: false })
    parts.push({ text: found[0], match: true })
    start = found.index + found[0].length
  }
  if (start < text.length) parts.push({ text: text.slice(start), match: false })
  return parts
}

onMounted(() => loadConversations())
</script>
