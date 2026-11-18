<template>
  <TextInput
    v-if="field"
    v-model="model"
    :label="setting.label"
    :description="setting.description"
    :placeholder="setting.placeholder"
    class="w-full"
    :class="{ 'sm:col-span-2': setting.wide }"
  >
    <template #label>
      {{ setting.label }}<span v-if="unsaved" class="unsaved-dot" aria-hidden="true" />
    </template>
  </TextInput>
  <div v-else-if="stacked" class="py-3.5">
    <div class="flex items-start justify-between gap-4">
      <div>
        <span class="text-base-medium leading-tighter block text-ink-gray-8">
          {{ setting.label }}<span v-if="unsaved" class="unsaved-dot" aria-hidden="true" />
        </span>
        <div v-if="setting.description" class="mt-1 text-base leading-5 text-ink-gray-6">
          {{ setting.description }}
        </div>
      </div>
      <Button
        v-if="setting.type === 'emojis' && !isBuiltInSet"
        variant="ghost"
        @click="model = [...defaultQuickReactionEmojis]"
      >
        Reset to default
      </Button>
    </div>
    <div v-if="setting.type === 'emojis'" class="mt-3 flex flex-wrap items-center gap-1">
      <div v-for="(emoji, index) in emojis" :key="emoji" class="group relative">
        <EmojiPicker side="bottom" align="start" @select="(picked) => setEmoji(index, picked)">
          <template #trigger>
            <button
              type="button"
              class="flex size-8 items-center justify-center rounded-5 border border-outline-gray-1 bg-surface-base text-lg font-[emoji] hover:bg-surface-gray-2"
              :aria-label="`Change ${emoji}`"
            >
              {{ emoji }}
            </button>
          </template>
        </EmojiPicker>
        <button
          v-if="emojis.length > 1"
          type="button"
          class="absolute -right-1 -top-1 hidden size-4 items-center justify-center rounded-full bg-surface-gray-7 text-ink-white group-hover:flex focus-visible:flex"
          :aria-label="`Remove ${emoji}`"
          @click="removeEmoji(index)"
        >
          <span class="lucide-x size-2.5" aria-hidden="true" />
        </button>
      </div>
      <EmojiPicker
        v-if="emojis.length < quickReactionSlotCount"
        side="bottom"
        align="start"
        @select="(picked) => setEmoji(emojis.length, picked)"
      >
        <template #trigger>
          <button
            type="button"
            class="flex size-8 items-center justify-center rounded-5 bg-surface-gray-2 text-ink-gray-6 transition hover:bg-surface-gray-3"
            aria-label="Add a quick reaction"
          >
            <span class="lucide-smile-plus size-4" aria-hidden="true" />
          </button>
        </template>
      </EmojiPicker>
    </div>
    <Textarea
      v-else
      v-model="model"
      class="mt-3 w-full !min-h-20 resize-none [field-sizing:content]"
      :placeholder="setting.placeholder"
      :aria-label="setting.label"
    />
  </div>
  <SettingsRow
    v-else
    :title="setting.label"
    :description="setting.description"
    :class="{ 'unsaved-row': unsaved }"
  >
    <Switch v-if="setting.type === 'switch'" v-model="model" :aria-label="setting.label" />
    <TextInput
      v-else-if="setting.type === 'number'"
      v-model="model"
      type="number"
      :min="0"
      class="w-20"
      :aria-label="setting.label"
    />
    <TextInput
      v-else-if="setting.type === 'text'"
      v-model="model"
      class="w-56"
      :placeholder="setting.placeholder"
      :aria-label="setting.label"
    />
    <Select
      v-else-if="setting.type === 'select'"
      v-model="model"
      class="w-56"
      :options="setting.options?.map((option) => ({ label: option, value: option }))"
      :aria-label="setting.label"
    />
    <MultiSelect
      v-else-if="setting.type === 'multiselect' || setting.type === 'communities'"
      v-model="model"
      class="w-56"
      :options="multiOptions"
      :placeholder="setting.placeholder"
      :aria-label="setting.label"
    />
    <Password
      v-else-if="setting.type === 'password'"
      v-model="model"
      class="w-56"
      :aria-label="setting.label"
    />
    <div v-else-if="setting.type === 'image'" class="flex items-center gap-3">
      <button
        v-if="model"
        type="button"
        class="flex size-8 items-center justify-center overflow-hidden rounded border border-outline-gray-2 hover:border-outline-gray-3"
        :aria-label="`Preview ${setting.label}`"
        @click="previewOpen = true"
      >
        <img :src="model" alt="" class="size-6 object-contain" />
      </button>
      <div
        v-else
        class="flex size-8 items-center justify-center rounded border border-outline-gray-2"
      >
        <span class="lucide-image size-4 text-ink-gray-4" aria-hidden="true" />
      </div>
      <Button v-if="model" variant="ghost" @click="setImage('')">Remove</Button>
      <ImageUploader
        kind="siteLogo"
        @success="(file) => setImage(file.file_url)"
        @failure="uploadFailed"
      >
        <template #default="{ openFileSelector, uploading }">
          <Button :loading="uploading" @click="openFileSelector">
            {{ model ? 'Change' : 'Upload' }}
          </Button>
        </template>
      </ImageUploader>
      <ImagePreview v-model:show="previewOpen" :image-url="model" />
    </div>
  </SettingsRow>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  Button,
  MultiSelect,
  Password,
  Select,
  SettingsRow,
  Switch,
  TextInput,
  Textarea,
  toast,
} from 'frappe-ui'
import EmojiPicker from '@/components/EmojiPicker.vue'
import ImagePreview from '@/components/ImagePreview.vue'
import ImageUploader from '@/components/ImageUploader.vue'
import { communities } from '@/data/communities'
import { defaultQuickReactionEmojis, quickReactionSlotCount } from '@/data/reactionPreferences'
import type { AdminSetting } from './sections'

const props = defineProps<{ setting: AdminSetting; field?: boolean; unsaved?: boolean }>()
const model = defineModel<any>()
const emit = defineEmits<{ save: [] }>()

const stacked = computed(() => ['textarea', 'list', 'emojis'].includes(props.setting.type))
const previewOpen = ref(false)

function setImage(url: string) {
  model.value = url
  emit('save')
}

function uploadFailed(error: unknown) {
  toast.error((error as Error)?.message || 'Could not upload the image')
}

const multiOptions = computed(() =>
  props.setting.type === 'communities'
    ? (communities.data || []).map((community) => ({
        label: community.title,
        value: community.name,
      }))
    : (props.setting.options || []).map((option) => ({ label: option, value: option })),
)

const isBuiltInSet = computed(
  () => JSON.stringify(model.value || []) === JSON.stringify(defaultQuickReactionEmojis),
)

const emojis = computed(() => (model.value as string[]) || [])

function setEmoji(index: number, emoji: string) {
  const next = [...emojis.value]
  if (next.includes(emoji) && next[index] !== emoji) {
    toast.error(`${emoji} is already in the set`)
    return
  }
  next[index] = emoji
  model.value = next
}

function removeEmoji(index: number) {
  model.value = emojis.value.filter((_, position) => position !== index)
}
</script>
<style scoped>
.unsaved-dot,
.unsaved-row > :deep(div:first-child > :first-child::after) {
  @apply ml-1.5 inline-block size-1.5 rounded-full bg-surface-gray-7 align-middle;
}
.unsaved-row > :deep(div:first-child > :first-child::after) {
  content: '';
}
</style>
