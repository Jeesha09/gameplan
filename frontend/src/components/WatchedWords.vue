<template>
  <div class="text-ink-gray-9">
    <div class="flex items-center justify-between gap-3 pb-3">
      <TextInput
        v-model="search"
        class="min-w-0 max-w-sm flex-1"
        type="search"
        placeholder="Search words"
        aria-label="Search words"
      >
        <template #prefix>
          <span class="lucide-search size-4 text-ink-gray-5" aria-hidden="true" />
        </template>
      </TextInput>
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
    <form
      class="flex items-center gap-3 border-t border-outline-gray-1 pt-3"
      @submit.prevent="addWord"
    >
      <TextInput
        v-model="word"
        placeholder="Add a word or phrase, use * as a wildcard"
        aria-label="Word or phrase"
        class="min-w-0 flex-1"
      />
      <Select v-model="newRule" class="w-44" :options="ruleOptions" aria-label="Rule" />
      <Checkbox v-model="caseSensitive" label="Case sensitive" />
      <Button type="submit" variant="solid" :disabled="!word.trim()" :loading="saving">Add</Button>
    </form>
    <p class="pb-3 pt-2 text-p-sm text-ink-gray-6">{{ actionHints[newRule] }}</p>
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
          <Select
            class="w-44"
            :model-value="rule.action"
            :options="ruleOptions"
            :aria-label="`Rule for ${rule.word}`"
            @update:model-value="changeRule(rule, String($event))"
          />
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
      :title="search.trim() ? 'No words match' : 'No watched words yet'"
      :description="
        search.trim()
          ? 'Try another search.'
          : 'Add words one at a time above, or import a CSV. Download the sample CSV to see its format.'
      "
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
      <p class="mt-1 text-p-sm text-ink-gray-6">Each line shows the word and its rule.</p>
      <ul class="mt-3 text-base">
        <li v-for="entry in preview?.words" :key="entry" class="font-mono text-sm">{{ entry }}</li>
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
  Select,
  TextInput,
  Checkbox,
  Textarea,
  call,
  dialog,
  toast,
  type UploadedFile,
} from 'frappe-ui'
import { extractServerMessage } from '@/utils'
import ModerationEmpty from './moderation/ModerationEmpty.vue'
import ModerationPager from './moderation/ModerationPager.vue'
import ModerationRow from './moderation/ModerationRow.vue'
const props = defineProps<{ communityId: string }>()
const actions = ['Block', 'Censor', 'Require approval', 'Flag']
const ruleOptions = actions.map((value) => ({ label: value, value }))
const actionHints: Record<string, string> = {
  Block: 'Posts containing these words are refused. The author sees which words matched.',
  Censor: 'These words are masked wherever posts are shown. The original text is kept.',
  'Require approval':
    'Posts containing these words wait for a moderator before they are published.',
  Flag: 'Posts are published, and a report is opened for moderators to review.',
}
const testOpen = ref(false)
const open = (url: string) => window.open(url, '_self')
const newRule = ref('Block'),
  search = ref(''),
  word = ref(''),
  caseSensitive = ref(false),
  start = ref(0),
  hasMore = ref(false)
type Rule = { name: string; word: string; action: string; case_sensitive: number }
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
      { community: props.communityId, query: search.value.trim(), start: start.value },
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
async function previewFile(uploaded: UploadedFile) {
  if (!uploaded.name) {
    error.value = 'Could not read the uploaded file. Upload it again.'
    return
  }
  file.value = uploaded.name
  error.value = ''
  try {
    preview.value = await call('gameplan.watched_words.upload', {
      community: props.communityId,
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
      action: newRule.value,
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
    message: `Remove “${rule.word}” from the ${rule.action} rule?`,
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
    new URLSearchParams({ community: props.communityId, sample: sample ? '1' : '0' })
  )
}
async function changeRule(rule: Rule, action: string) {
  if (action === rule.action) return
  error.value = ''
  try {
    await call('gameplan.watched_words.set_action', {
      community: props.communityId,
      name: rule.name,
      action,
    })
    rule.action = action
  } catch (e) {
    showError(e)
    // The list shows what is saved, so the dropdown goes back to it.
    await load()
  }
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
  [() => props.communityId, search],
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
