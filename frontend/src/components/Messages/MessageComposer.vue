<template>
  <div
    class="rounded-5 border border-outline-gray-2 bg-surface-base transition focus-within:border-outline-gray-4"
    @keydown.capture="onKeydown"
    @paste.capture="onPaste"
    @drop.capture="onDrop"
  >
    <div
      v-if="editing"
      class="flex items-center justify-between gap-2 border-b border-outline-gray-1 py-1 pl-3 pr-1.5"
    >
      <span class="flex items-center gap-1.5 text-sm text-ink-gray-5">
        <span class="lucide-pen-line size-3.5" />
        Editing message
      </span>
      <Button variant="ghost" size="sm" icon="lucide-x" label="Cancel editing" @click="cancel" />
    </div>
    <div
      v-else-if="replyingTo"
      class="flex items-start justify-between gap-2 border-b border-outline-gray-1 py-1.5 pl-3 pr-1.5"
    >
      <div class="min-w-0 text-sm">
        <div class="flex items-center gap-1.5 text-ink-gray-5">
          <span class="lucide-reply size-3.5 shrink-0" />
          <span class="shrink-0">Replying to</span>
          <span class="truncate text-sm-medium text-ink-gray-7">
            {{
              replyingTo.owner === sessionUser.name
                ? 'yourself'
                : useUser(replyingTo.owner).full_name
            }}
          </span>
        </div>
        <p class="mt-0.5 truncate text-ink-gray-5">{{ replySnippet }}</p>
      </div>
      <Button
        variant="ghost"
        size="sm"
        icon="lucide-x"
        label="Cancel reply"
        @click="emit('cancelReply')"
      />
    </div>
    <div v-if="attachments.length && !editing" class="flex flex-wrap gap-2 px-3 pt-3">
      <div
        v-for="item in attachments"
        :key="item.id"
        class="relative"
        :class="item.kind === 'file' ? 'w-56 max-w-full' : 'size-16'"
      >
        <div
          v-if="item.kind === 'file'"
          class="flex items-center gap-2 rounded-5 border border-outline-gray-2 py-1.5 pl-1.5 pr-8"
        >
          <span class="grid size-8 shrink-0 place-items-center rounded-5 bg-surface-gray-2">
            <span :class="fileIcon(item.file.name)" class="size-4 text-ink-gray-6" />
          </span>
          <span class="min-w-0 flex-1 leading-tight">
            <span class="block truncate text-sm-medium text-ink-gray-8">{{ item.file.name }}</span>
            <span class="mt-0.5 block text-xs text-ink-gray-5">
              {{ item.uploaded ? formatBytes(item.file.size) : `Uploading ${item.progress}%` }}
            </span>
          </span>
        </div>
        <div
          v-else
          class="size-full overflow-hidden rounded-5 border border-outline-gray-2 bg-surface-gray-2"
        >
          <img
            v-if="item.kind === 'image'"
            :src="item.preview"
            :alt="item.file.name"
            class="size-full object-cover"
          />
          <video v-else :src="item.preview" muted class="size-full object-cover" />
          <span
            v-if="item.kind === 'video' && item.uploaded"
            class="absolute inset-0 grid place-items-center"
          >
            <span class="lucide-play size-5 text-white drop-shadow" />
          </span>
          <span
            v-if="!item.uploaded"
            class="absolute inset-0 grid place-items-center rounded-5 bg-black/40 text-xs text-white"
          >
            {{ item.progress }}%
          </span>
        </div>
        <button
          type="button"
          class="absolute grid size-5 place-items-center rounded-full border border-outline-gray-2 bg-surface-base text-ink-gray-6 shadow-sm transition-colors hover:text-ink-gray-9"
          :class="item.kind === 'file' ? 'right-2 top-1/2 -translate-y-1/2' : '-right-1.5 -top-1.5'"
          :aria-label="`Remove ${item.file.name}`"
          @click="remove(item)"
        >
          <span class="lucide-x size-3" />
        </button>
      </div>
    </div>
    <div class="px-3 pt-2">
      <GPEditor
        ref="gp"
        :extensions="extensions"
        :content="content"
        :placeholder="placeholder"
        :editor-class="['prose-v3 max-w-none']"
        min-height="3rem"
        max-height="10rem"
        @change="content = $event"
      />
    </div>
    <div class="flex items-center justify-between gap-2 px-1.5 pb-1.5 pt-1">
      <div class="flex items-center gap-1">
        <TooltipProvider>
          <EmojiPicker @select="insertEmoji">
            <template #trigger>
              <Button size="sm" variant="ghost" icon="lucide-smile" label="Emoji" tooltip="Emoji" />
            </template>
          </EmojiPicker>
          <span class="mx-1 h-5 border-l border-outline-gray-2" aria-hidden="true" />
          <Button
            size="sm"
            variant="ghost"
            icon="lucide-image"
            label="Image"
            tooltip="Image"
            :disabled="Boolean(editing)"
            @click="pick('image')"
          />
          <Button
            size="sm"
            variant="ghost"
            icon="lucide-video"
            label="Video"
            tooltip="Video"
            :disabled="Boolean(editing)"
            @click="pick('video')"
          />
          <Button
            size="sm"
            variant="ghost"
            icon="lucide-paperclip"
            label="Attach"
            tooltip="Attach file"
            :disabled="Boolean(editing)"
            @click="pick('file')"
          />
        </TooltipProvider>
      </div>
      <Button
        variant="solid"
        :icon="editing ? 'lucide-check' : 'lucide-arrow-up'"
        :label="editing ? 'Save' : 'Send'"
        :disabled="!canSend"
        :loading="sending"
        @click="submit"
      />
    </div>
    <input
      ref="picker"
      type="file"
      class="hidden"
      :accept="ACCEPT[pickKind]"
      :multiple="pickKind !== 'video'"
      @change="onPick"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, useTemplateRef, watch } from 'vue'
import { Button, TooltipProvider, toast, type UploadedFile } from 'frappe-ui'
import { CommentKit, SlashCommands } from 'frappe-ui/editor'
import type { Editor } from '@tiptap/core'
import EmojiPicker from '@/components/EmojiPicker.vue'
import { uploadFile } from '@/components/editor/config'
import { CustomEmojiExtension } from '@/components/editor/customEmojiExtension'
import GPEditor from '@/components/editor/GPEditor.vue'
import type { DirectMessage } from '@/data/messages'
import { useSessionUser, useUser } from '@/data/users'
import { extractServerMessage, isEditorContentEmpty } from '@/utils'
import { isImageEmoji } from '@/utils/emoji'
import { useIsMobile } from '@/utils/useIsMobile'
import { fileIcon, formatBytes } from './messageFiles'

const props = defineProps<{
  placeholder: string
  send: (content: string) => Promise<void>
  editing?: DirectMessage | null
  replyingTo?: DirectMessage | null
}>()

const emit = defineEmits<{
  cancel: []
  cancelReply: []
}>()

type SlashProps = { query: string; editor: Editor }

const extensions = [
  CommentKit.configure({
    heading: false,
    imageGroup: false,
    imageViewer: false,
    contentPaste: false,
    mention: false,
    tag: false,
  }),
  SlashCommands.extend({
    addOptions() {
      const parent = this.parent?.() as {
        suggestion: { items: (props: SlashProps) => { group?: string }[] }
      }
      return {
        ...parent,
        suggestion: {
          ...parent.suggestion,
          items: (props: SlashProps) =>
            parent.suggestion.items(props).filter((item) => item.group !== 'Media'),
        },
      }
    },
  }),
  CustomEmojiExtension,
]

function insertEmoji(emoji: string) {
  const chain = gp.value?.editor?.chain().focus()
  if (!chain) return
  if (isImageEmoji(emoji)) chain.insertCustomEmoji({ src: emoji, alt: 'emoji' }).run()
  else chain.insertContent(emoji).run()
}

type Kind = 'image' | 'video' | 'file'
type Pending = {
  id: number
  file: File
  kind: Kind
  preview?: string
  progress: number
  uploaded?: UploadedFile
  controller: AbortController
}

const ACCEPT: Record<Kind, string> = { image: 'image/*', video: 'video/*', file: '' }
const picker = useTemplateRef<HTMLInputElement>('picker')
const pickKind = ref<Kind>('image')
const attachments = ref<Pending[]>([])
let nextId = 0

async function pick(kind: Kind) {
  pickKind.value = kind
  await nextTick()
  picker.value?.click()
}

function onPick(event: Event) {
  const input = event.target as HTMLInputElement
  addFiles(input.files)
  input.value = ''
}

function onPaste(event: ClipboardEvent) {
  if (!event.clipboardData?.files.length || props.editing) return
  event.preventDefault()
  event.stopPropagation()
  addFiles(event.clipboardData.files)
}

function onDrop(event: DragEvent) {
  if (!event.dataTransfer?.files.length || props.editing) return
  event.preventDefault()
  event.stopPropagation()
  addFiles(event.dataTransfer.files)
}

function kindOf(file: File): Kind {
  if (file.type.startsWith('image/')) return 'image'
  if (file.type.startsWith('video/')) return 'video'
  return 'file'
}

function addFiles(files: FileList | null) {
  for (const file of files ?? []) {
    const kind = kindOf(file)
    const item = reactive<Pending>({
      id: nextId++,
      file,
      kind,
      preview: kind === 'file' ? undefined : URL.createObjectURL(file),
      progress: 0,
      controller: new AbortController(),
    })
    attachments.value.push(item)
    upload(item)
  }
  focusEditor()
}

async function upload(item: Pending) {
  try {
    item.uploaded = await uploadFile(item.file, {
      signal: item.controller.signal,
      onProgress: ({ percent }) => (item.progress = Math.round(percent)),
    })
  } catch {
    if (item.controller.signal.aborted) return
    toast.error(`Could not upload ${item.file.name}`)
    remove(item)
  }
}

function release(item: Pending) {
  item.controller.abort()
  if (item.preview) URL.revokeObjectURL(item.preview)
}

function remove(item: Pending) {
  release(item)
  attachments.value = attachments.value.filter((other) => other.id !== item.id)
}

function clearAttachments() {
  attachments.value.forEach(release)
  attachments.value = []
}

onBeforeUnmount(clearAttachments)

function escapeAttribute(value: string) {
  return value.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')
}

function attachmentHtml() {
  const order: Kind[] = ['image', 'video', 'file']
  return order
    .flatMap((kind) => attachments.value.filter((item) => item.kind === kind))
    .map(({ kind, file, uploaded }) => {
      const url = escapeAttribute(uploaded?.file_url ?? '')
      if (kind === 'image') return `<img src="${url}">`
      if (kind === 'video') return `<video src="${url}" controls=""></video>`
      const name = escapeAttribute(file.name)
      return `<p><a data-attachment="" data-file-name="${name}" data-file-size="${file.size}" href="${url}" rel="noopener noreferrer">${name}</a></p>`
    })
    .join('')
}

function slashMenuOpen(editor: Editor) {
  return editor.state.plugins.some(
    (plugin) =>
      (plugin as unknown as { key: string }).key.startsWith('slashCommandSuggestion') &&
      plugin.getState(editor.state)?.active,
  )
}

const isMobile = useIsMobile()
const sessionUser = useSessionUser()
const gp = useTemplateRef<InstanceType<typeof GPEditor>>('gp')
const content = ref('')
const sending = ref(false)
let draft = ''

const attaching = computed(() => !props.editing && attachments.value.length > 0)
const canSend = computed(
  () =>
    (!attaching.value || attachments.value.every((item) => item.uploaded)) &&
    (attaching.value || !isEditorContentEmpty(content.value)),
)

const replySnippet = computed(() => {
  const html = props.replyingTo?.content ?? ''
  return new DOMParser().parseFromString(html, 'text/html').body.textContent?.trim() ?? ''
})

function focusEditor() {
  setTimeout(() => gp.value?.editor?.commands.focus('end'))
}

watch(
  () => props.replyingTo,
  (message) => {
    if (message) focusEditor()
  },
  { flush: 'post' },
)

function setContent(value: string) {
  content.value = value
  gp.value?.editor?.commands.setContent(value)
  focusEditor()
}

watch(
  () => props.editing,
  (message, previous) => {
    if (message && !previous) draft = content.value
    setContent(message ? message.content : draft)
    if (!message) draft = ''
  },
  { flush: 'post' },
)

async function submit() {
  if (sending.value || !canSend.value) return
  const wasEditing = Boolean(props.editing)
  const text = isEditorContentEmpty(content.value) ? '' : content.value
  sending.value = true
  try {
    await props.send(wasEditing ? content.value : attachmentHtml() + text)
    if (!wasEditing) {
      setContent('')
      clearAttachments()
    }
  } catch (error) {
    toast.error(
      extractServerMessage(error) ||
        (wasEditing ? 'Could not save your message' : 'Could not send your message'),
    )
  } finally {
    sending.value = false
  }
}

function cancel() {
  emit('cancel')
}

function onKeydown(event: KeyboardEvent) {
  const editor = gp.value?.editor
  if (editor && slashMenuOpen(editor)) return
  if (event.key === 'Escape' && props.editing) {
    event.preventDefault()
    cancel()
    return
  }
  if (event.key === 'Escape' && props.replyingTo) {
    event.preventDefault()
    emit('cancelReply')
    return
  }
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing || isMobile.value) return
  if (editor?.isActive('listItem') || editor?.isActive('codeBlock')) return
  event.preventDefault()
  event.stopPropagation()
  submit()
}
</script>
