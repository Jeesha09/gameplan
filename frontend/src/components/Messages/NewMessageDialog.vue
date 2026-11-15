<template>
  <Dialog v-model:open="show" size="md" bare @after-leave="reset">
    <div class="flex max-h-[min(520px,calc(100dvh-8rem))] flex-col">
      <div class="flex shrink-0 items-center justify-between px-4 pb-2 pt-3">
        <Dialog.Title as-child>
          <h2 class="text-md font-medium text-ink-gray-9">New message</h2>
        </Dialog.Title>
        <Dialog.Close as-child>
          <Button variant="ghost" label="Close" icon="lucide-x" />
        </Dialog.Close>
      </div>
      <Dialog.Description as-child>
        <p class="sr-only">Search for someone to message.</p>
      </Dialog.Description>

      <div class="shrink-0 px-4 pb-3">
        <TextInput
          v-model="query"
          class="w-full"
          placeholder="Search by name or email"
          aria-label="Search people"
          autofocus
          @keydown="onKeydown"
        >
          <template #prefix>
            <span class="lucide-search size-4 text-ink-gray-4" aria-hidden="true" />
          </template>
        </TextInput>
      </div>

      <ScrollArea class="min-h-0 flex-1 border-t border-outline-gray-1" viewport-class="p-2">
        <div v-if="searching && loading && !people.length" class="space-y-1" role="status">
          <div v-for="n in 4" :key="n" class="flex h-12 items-center gap-3 px-2">
            <Skeleton class="size-8 shrink-0 rounded-full" />
            <Skeleton class="h-3.5 w-40 rounded-4" />
          </div>
        </div>

        <EmptyStateBox v-else-if="searching && !people.length" class="my-4">
          <span class="lucide-search-x size-5 text-ink-gray-4" aria-hidden="true" />
          <div class="mt-2 text-p-sm text-ink-gray-5">Nobody matches this search</div>
        </EmptyStateBox>

        <div v-else-if="!people.length" class="flex flex-col items-center px-6 py-8 text-center">
          <span class="lucide-messages-square size-7 text-ink-gray-4" aria-hidden="true" />
          <p class="mt-3 text-base-medium text-ink-gray-8">Start a conversation</p>
          <p class="mt-1 text-base text-ink-gray-5">
            Search for anyone in your community to send them a message
          </p>
        </div>

        <template v-else>
          <div v-if="!searching" class="flex items-center justify-between pb-1 pl-2">
            <p class="text-sm-medium text-ink-gray-5">Recent</p>
            <Button variant="ghost" size="sm" @click="recentSearches = []">Clear</Button>
          </div>
          <button
            v-for="(user, index) in people"
            :key="user"
            type="button"
            class="flex h-12 w-full items-center gap-3 rounded-5 px-2 text-left transition-colors"
            :class="index === active ? 'bg-surface-gray-2' : 'hover:bg-surface-gray-2'"
            @mouseenter="active = index"
            @click="open(user)"
          >
            <UserAvatar :user="user" size="lg" class="shrink-0" />
            <span class="truncate text-base text-ink-gray-8">{{ useUser(user).full_name }}</span>
          </button>
        </template>
      </ScrollArea>
    </div>
  </Dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useLocalStorage } from '@vueuse/core'
import { Button, Dialog, ScrollArea, Skeleton, TextInput } from 'frappe-ui'
import EmptyStateBox from '@/components/EmptyStateBox.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { openDirectMessage } from '@/data/messages'
import { useSessionUser, useUser, useUserSearch } from '@/data/users'

const RECENT_LIMIT = 8

const show = defineModel<boolean>({ default: false })

const router = useRouter()
const sessionUser = useSessionUser()
const query = ref('')
const active = ref(0)
const searching = computed(() => Boolean(query.value.trim()))

const { results, loading } = useUserSearch(() =>
  show.value && searching.value
    ? { query: query.value.trim(), include_guests: false, direct_messages: true }
    : null,
)

const recentSearches = useLocalStorage<string[]>(
  `gameplan:recentMessageSearches:${sessionUser.name}`,
  [],
)

const recent = computed(() =>
  recentSearches.value.filter(
    (user) => user !== sessionUser.name && useUser(user).direct_messages_enabled !== 0,
  ),
)

const people = computed(() =>
  searching.value
    ? results.value.map((user) => user.name).filter((user) => user !== sessionUser.name)
    : recent.value,
)

watch(people, () => (active.value = 0))

function onKeydown(event: KeyboardEvent) {
  const count = people.value.length
  if (!count) return
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    active.value = (active.value + (event.key === 'ArrowDown' ? 1 : count - 1)) % count
  } else if (event.key === 'Enter') {
    event.preventDefault()
    open(people.value[active.value])
  }
}

function reset() {
  query.value = ''
  active.value = 0
}

async function open(user: string) {
  recentSearches.value = [user, ...recentSearches.value.filter((item) => item !== user)].slice(
    0,
    RECENT_LIMIT,
  )
  show.value = false
  await openDirectMessage(router, user)
}
</script>
