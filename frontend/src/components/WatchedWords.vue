<template>
  <div class="text-ink-gray-9">
    <div class="flex items-center justify-between gap-3 pb-2">
      <TabButtons v-model="action" :options="actions.map((value) => ({ label: value, value }))" />
      <div class="flex items-center gap-1">
        <Button variant="ghost" icon-left="lucide-flask-conical" @click="testOpen = true"
          >Test rules</Button
        >
        <FileUploader
          :file-types="['.csv']"
          :private="true"
          :validate-file="validateFile"
          @success="previewFile"
          @failure="showError"
        >
          <template #default="{ openFileSelector, uploading, progress }">
            <Dropdown
              align="end"
              :button="{
                icon: 'lucide-more-horizontal',
                variant: 'ghost',
                label: uploading ? `Uploading ${progress}%` : 'Import and export',
                loading: uploading,
              }"
              :options="[
                { label: 'Import from CSV', icon: 'lucide-upload', onClick: openFileSelector },
                {
                  label: 'Download this list',
                  icon: 'lucide-download',
                  onClick: () => open(downloadUrl(false)),
                },
                {
                  label: 'Download sample CSV',
                  icon: 'lucide-file-text',
                  onClick: () => open(downloadUrl(true)),
                },
              ]"
            />
          </template>
        </FileUploader>
      </div>
    </div>
    <p class="pb-4 text-p-sm text-ink-gray-6">{{ actionHints[action] }}</p>
    <form
      class="flex items-center gap-3 border-t border-outline-gray-1 py-3"
      @submit.prevent="addWord"
    >
      <TextInput
        v-model="word"
        placeholder="Add a word or phrase, use * as a wildcard"
        aria-label="Word or phrase"
        class="min-w-0 flex-1"
      />
      <Checkbox v-model="caseSensitive" label="Case sensitive" />
      <Button type="submit" variant="solid" :disabled="!word.trim()" :loading="saving">Add</Button>
    </form>
    <ErrorMessage v-if="error" class="pb-3" :message="error" />
    <div v-if="items.length" class="border-t border-outline-gray-1">
      <ModerationRow v-for="rule in items" :key="rule.name">
        <template #title
          ><span class="font-mono">{{ rule.word }}</span></template
        >
        <template #status>
          <Badge v-if="rule.case_sensitive" label="Case sensitive" />
        </template>
        <template #actions>
          <Button
            variant="ghost"
            icon="lucide-trash-2"
            :aria-label="`Delete ${rule.word}`"
            @click="deleteRule(rule)"
          />
        </template>
      </ModerationRow>
    </div>
    <ModerationEmpty
      v-else
      icon="lucide-text-search"
      :title="`No ${action.toLowerCase()} rules`"
      description="Add words one at a time above, or import a CSV list."
    />
    <ModerationPager
      :previous="start > 0"
      :next="hasMore"
      @previous="start -= 40"
      @next="start += 40"
    />
    <Dialog v-model:open="testOpen" title="Test rules">
      <Textarea
        v-model="testText"
        placeholder="Paste a post or a few words to see which rules match"
        :rows="5"
        aria-label="Text to test"
      />
      <div v-if="Object.keys(results).length" class="mt-4 divide-y divide-outline-gray-1">
        <div v-for="(words, key) in results" :key="key" class="flex items-center gap-3 py-2">
          <span class="w-32 shrink-0 text-p-sm text-ink-gray-6">{{ key }}</span>
          <span class="flex flex-wrap gap-1">
            <Badge v-for="match in words" :key="match" :label="match" />
            <span v-if="!words.length" class="text-p-sm text-ink-gray-5">No matches</span>
          </span>
        </div>
      </div>
      <template #actions>
        <Button variant="solid" :disabled="!testText.trim()" @click="testRules">Test</Button>
      </template>
    </Dialog>
    <Dialog v-model:open="previewOpen" title="Preview CSV import">
      <p class="text-base">
        {{ preview?.added }} new rules · {{ preview?.duplicates }} duplicates skipped. Existing
        rules stay unchanged.
      </p>
      <ul class="mt-3 text-base">
        <li v-for="entry in preview?.words" :key="entry">{{ entry }}</li>
      </ul>
      <p v-if="(preview?.added || 0) > 40" class="mt-2 text-base text-ink-gray-5">
        Showing the first 40 new rules.
      </p>
      <ErrorMessage v-if="error" :message="error" />
      <template #actions
        ><Button variant="solid" :loading="saving" @click="applyImport"
          >Import {{ preview?.added }} rules</Button
        ></template
      >
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  Badge,
  Button,
  Dialog,
  Dropdown,
  ErrorMessage,
  FileUploader,
  TabButtons,
  TextInput,
  Checkbox,
  Textarea,
  call,
  dialog,
  toast,
} from 'frappe-ui'
import { extractServerMessage } from '@/utils'
import ModerationEmpty from './moderation/ModerationEmpty.vue'
import ModerationPager from './moderation/ModerationPager.vue'
import ModerationRow from './moderation/ModerationRow.vue'
const props = defineProps<{ communityId: string }>()
const actions = ['Block', 'Censor', 'Require approval', 'Flag']
const actionHints: Record<string, string> = {
  Block: 'Posts containing these words are refused. The author sees which words matched.',
  Censor: 'These words are masked wherever posts are shown. The original text is kept.',
  'Require approval':
    'Posts containing these words wait for a moderator before they are published.',
  Flag: 'Posts are published, and a report is opened for moderators to review.',
}
const testOpen = ref(false)
const open = (url: string) => window.open(url, '_self')
const action = ref('Block'),
  word = ref(''),
  caseSensitive = ref(false),
  start = ref(0),
  hasMore = ref(false)
type Rule = { name: string; word: string; case_sensitive: number }
type Preview = { expected: string; added: number; duplicates: number; words: string[] }
const items = ref<Rule[]>([]),
  preview = ref<Preview | null>(null),
  previewOpen = ref(false),
  file = ref(''),
  error = ref(''),
  saving = ref(false)
const testText = ref(''),
  results = ref<Record<string, string[]>>({})
function showError(e: unknown) {
  error.value = extractServerMessage(e) || 'Could not update watched words'
}
let loadRequest = 0
async function load() {
  const request = ++loadRequest
  items.value = []
  error.value = ''
  try {
    const result = await call<{ items: Rule[]; has_more: boolean }>(
      'gameplan.watched_words.rules',
      { community: props.communityId, action: action.value, start: start.value },
    )
    if (request !== loadRequest) return
    items.value = result.items
    hasMore.value = result.has_more
  } catch (e) {
    if (request === loadRequest) showError(e)
  }
}
function validateFile(file: File) {
  if (file.size > 1024 * 1024) return 'CSV uploads must be at most 1 MB'
}
async function previewFile(uploaded: { name: string }) {
  file.value = uploaded.name
  error.value = ''
  try {
    preview.value = await call('gameplan.watched_words.upload', {
      community: props.communityId,
      action: action.value,
      file: file.value,
    })
    previewOpen.value = true
  } catch (e) {
    showError(e)
  }
}
async function applyImport() {
  saving.value = true
  try {
    await call('gameplan.watched_words.upload', {
      community: props.communityId,
      action: action.value,
      file: file.value,
      expected: preview.value?.expected,
    })
    previewOpen.value = false
    toast.success('Watched words imported')
    await load()
  } catch (e) {
    showError(e)
  } finally {
    saving.value = false
  }
}
async function addWord() {
  saving.value = true
  try {
    await call('gameplan.watched_words.add', {
      community: props.communityId,
      action: action.value,
      word: word.value,
      case_sensitive: caseSensitive.value,
    })
    word.value = ''
    await load()
  } catch (e) {
    showError(e)
  } finally {
    saving.value = false
  }
}
function deleteRule(rule: Rule) {
  dialog.danger({
    title: 'Delete watched word',
    message: `Remove “${rule.word}” from ${action.value}?`,
    confirmLabel: 'Delete rule',
    onConfirm: async () => {
      try {
        await call('gameplan.watched_words.remove', {
          community: props.communityId,
          name: rule.name,
        })
        await load()
      } catch (e) {
        showError(e)
      }
    },
  })
}
function downloadUrl(sample: boolean) {
  return (
    '/api/method/gameplan.watched_words.download?' +
    new URLSearchParams({
      community: props.communityId,
      action: action.value,
      sample: sample ? '1' : '0',
    })
  )
}
async function testRules() {
  try {
    results.value = await call('gameplan.watched_words.test', {
      community: props.communityId,
      content: testText.value,
    })
  } catch (e) {
    showError(e)
  }
}
watch(
  [() => props.communityId, action],
  () => {
    start.value = 0
    previewOpen.value = false
    results.value = {}
    load()
  },
  { immediate: true },
)
watch(start, load)
</script>
