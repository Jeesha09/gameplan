<template>
  <aside class="flex min-h-0 flex-col bg-surface-base">
    <header class="flex min-h-12 shrink-0 items-center justify-between border-b px-5">
      <span class="text-lg font-semibold text-ink-gray-9">Details</span>
      <Button variant="ghost" icon="lucide-x" label="Close details" @click="emit('close')" />
    </header>
    <ScrollArea class="min-h-0 flex-1" viewport-class="p-5">
      <div class="flex flex-col items-center text-center">
        <UserAvatar :user="person" size="3xl" />
        <p class="mt-3 text-lg-medium text-ink-gray-9">{{ user.full_name }}</p>
        <p v-if="user.bio" class="mt-1 line-clamp-3 text-base text-ink-gray-6">{{ user.bio }}</p>
      </div>
      <TabButtons
        class="mt-6"
        fluid
        :options="[
          { value: 'files', label: 'Files' },
          { value: 'links', label: 'Links' },
        ]"
        v-model="tab"
      />
      <TextInput
        v-model="query"
        class="mt-3 w-full"
        :placeholder="tab === 'files' ? 'Search files' : 'Search links'"
        :debounce="300"
      >
        <template #prefix>
          <span class="lucide-search h-4 w-4 text-ink-gray-4" />
        </template>
      </TextInput>

      <div v-if="!loaded" class="mt-4 grid grid-cols-3 gap-2">
        <div v-for="index in 6" :key="index" class="aspect-square rounded-5 bg-surface-gray-2" />
      </div>
      <p
        v-else-if="!(tab === 'files' ? files.length : links.length)"
        class="px-4 py-10 text-center text-base text-ink-gray-5"
      >
        {{ trimmed ? 'No results' : tab === 'files' ? 'No files yet' : 'No links yet' }}
      </p>
      <div v-else-if="tab === 'files'" class="mt-4 grid grid-cols-3 gap-2">
        <button
          v-for="(file, index) in files"
          :key="`${file.message}-${file.url}`"
          type="button"
          class="relative aspect-square overflow-hidden rounded-5 border border-outline-gray-2 bg-surface-gray-1 transition-colors hover:bg-surface-gray-2"
          :title="file.name"
          @click="viewing = index"
        >
          <img
            v-if="file.kind === 'image'"
            :src="file.url"
            :alt="file.name"
            loading="lazy"
            class="size-full object-cover"
          />
          <span v-else class="flex size-full flex-col items-center justify-center gap-1.5 p-2">
            <span
              :class="file.kind === 'video' ? 'lucide-play' : fileIcon(file.name)"
              class="size-5 shrink-0 text-ink-gray-6"
            />
            <span class="w-full truncate text-xs text-ink-gray-6">{{ file.name }}</span>
          </span>
        </button>
      </div>
      <div v-else class="mt-3">
        <a
          v-for="link in links"
          :key="`${link.message}-${link.url}`"
          :href="link.url"
          target="_blank"
          rel="noopener noreferrer"
          class="-mx-2 flex items-center gap-2.5 rounded-5 px-2 py-2 transition-colors hover:bg-surface-gray-2"
        >
          <span class="grid size-9 shrink-0 place-items-center rounded-5 bg-surface-gray-2">
            <span class="lucide-link size-4 text-ink-gray-6" />
          </span>
          <span class="min-w-0 flex-1 leading-tight">
            <span class="block truncate text-base-medium text-ink-gray-8">{{ link.text }}</span>
            <span class="mt-0.5 block truncate text-sm text-ink-gray-5">
              {{ hostname(link.url) }} · {{ relativeTimestamp(link.creation) }}
            </span>
          </span>
        </a>
      </div>
      <div v-if="loaded && hasMore" class="mt-3 flex justify-center">
        <Button variant="ghost" :loading="loading" @click="load(true)">Load more</Button>
      </div>
    </ScrollArea>
    <AttachmentViewer
      v-if="viewing !== null"
      :files="files"
      :start="viewing"
      @close="viewing = null"
    />
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button, ScrollArea, TabButtons, TextInput, toast } from 'frappe-ui'
import UserAvatar from '@/components/UserAvatar.vue'
import { getSharedMessages, type SharedMessage } from '@/data/messages'
import { useUser } from '@/data/users'
import { relativeTimestamp } from '@/utils'
import AttachmentViewer from './AttachmentViewer.vue'
import { fileIcon, messageFiles, messageLinks, type ViewerFile } from './messageFiles'

const props = defineProps<{
  conversation: string
  person: string
}>()

const emit = defineEmits<{ close: [] }>()
const tab = defineModel<'files' | 'links'>('tab', { required: true })

const user = computed(() => useUser(props.person))

const query = ref('')
const trimmed = computed(() => query.value.trim())
const shared = ref<SharedMessage[]>([])
const hasMore = ref(false)
const loaded = ref(false)
const loading = ref(false)
const viewing = ref<number | null>(null)
let request = 0

function matches(...values: string[]) {
  const needle = trimmed.value.toLowerCase()
  return !needle || values.some((value) => value.toLowerCase().includes(needle))
}

const files = computed<ViewerFile[]>(() =>
  shared.value.flatMap((message) =>
    messageFiles(message.content)
      .filter((file) => matches(file.name))
      .map((file) => ({
        ...file,
        owner: message.owner,
        creation: message.creation,
        message: message.name,
      })),
  ),
)

const links = computed(() =>
  shared.value.flatMap((message) =>
    messageLinks(message.content)
      .filter((link) => matches(link.url, link.text))
      .map((link) => ({ ...link, creation: message.creation, message: message.name })),
  ),
)

function hostname(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

async function load(more = false) {
  const current = ++request
  loading.value = true
  if (!more) loaded.value = false
  try {
    const page = await getSharedMessages(
      props.conversation,
      tab.value,
      trimmed.value,
      more ? shared.value.at(-1)?.name : undefined,
    )
    if (current !== request) return
    shared.value = more ? [...shared.value, ...page.messages] : page.messages
    hasMore.value = page.has_more
    loaded.value = true
  } catch {
    if (current !== request) return
    loaded.value = true
    toast.error(`Could not load ${tab.value}`)
  } finally {
    if (current === request) loading.value = false
  }
}

watch(
  () => [props.conversation, tab.value, trimmed.value],
  () => {
    viewing.value = null
    load()
  },
  { immediate: true },
)
</script>
