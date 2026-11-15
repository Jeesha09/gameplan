<template>
  <div class="group flex min-w-0 max-w-[75%] flex-col" :class="mine ? 'items-end' : 'items-start'">
    <span v-if="sender" class="mb-1 max-w-full truncate px-3 text-sm text-ink-gray-5">
      {{ sender }}
    </span>
    <component
      :is="tapForActions ? Dropdown : 'div'"
      class="max-w-full"
      v-bind="tapForActions ? menu : {}"
    >
      <div
        class="relative max-w-full overflow-hidden rounded-7 transition-shadow duration-700"
        :class="[
          !filesOnly && 'bg-surface-gray-2',
          !filesOnly && (hasMedia ? 'w-[max(18rem,33cqw)] p-1' : 'px-3 py-1.5'),
          highlighted && 'ring-2 ring-outline-gray-3',
        ]"
        @dblclick="onDoubleClick"
        @contextmenu="onContextMenu"
      >
        <button
          v-if="reply"
          type="button"
          class="mb-1.5 mt-1 block w-full min-w-0 border-l-2 border-outline-gray-3 text-left text-ink-gray-6 transition-colors hover:border-outline-gray-4 hover:bg-[rgba(0,0,0,0.02)] dark:hover:bg-[rgba(255,255,255,0.1)]"
          @click.stop="emit('jump', reply.name)"
        >
          <span class="flex min-w-0 items-center gap-2 px-2 pb-1 pt-1.5">
            <UserAvatar size="xs" :user="reply.owner" />
            <span class="truncate text-xs">{{ authorName(reply.owner) }}:</span>
          </span>
          <span class="line-clamp-3 px-2 pb-1.5 text-base">
            {{ reply.snippet }}
          </span>
        </button>
        <div
          data-slot="editor-content"
          class="ProseMirror prose prose-v3 relative max-w-none !whitespace-normal [&_img:not([data-emoji])]:max-h-80 [&_img:not([data-emoji])]:rounded-5 [&_img:not([data-emoji])]:cursor-zoom-in [&_video]:max-h-80 [&_video]:rounded-5"
          :class="hasMedia && mediaLayout"
          @pointerdown="onContentPointerdown"
          @click="onContentClick"
          v-html="html"
        />
        <div
          v-if="hoverActions"
          class="absolute right-0 top-0 flex items-start opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100 has-[[data-state=open]]:opacity-100"
          :class="
            frosted
              ? 'pr-2 pt-2'
              : 'bg-gradient-to-l from-surface-gray-2 from-40% to-transparent pl-12 pr-1.5 pt-1.5'
          "
        >
          <span
            v-if="frosted"
            class="flex rounded-3 bg-black/20 backdrop-blur-md [&_.lucide-more-horizontal]:!text-white [&_button]:!rounded-3 [&_button]:!bg-transparent"
          >
            <DropdownMoreOptions v-bind="menu" label="Message options" button-size="xs" />
          </span>
          <DropdownMoreOptions v-else v-bind="menu" label="Message options" button-size="xs" />
        </div>
      </div>
    </component>
    <MessageReactions
      v-if="hasReactions"
      class="mt-1"
      :reactions="message.reactions"
      :toggle-reaction="(emoji: string) => emit('react', emoji)"
    />
    <div v-if="footer" class="mt-1 flex items-center gap-1 px-1 text-xs text-ink-gray-5">
      <Tooltip :text="at.format(FULL_TIME)">
        <span>{{ footer }}</span>
      </Tooltip>
      <template v-if="seen">
        <span aria-hidden="true">·</span>
        <span v-if="isMobile">Seen {{ seenShort }}</span>
        <Tooltip v-else :text="`Seen ${seen.format(FULL_TIME)}`">
          <span>Seen</span>
        </Tooltip>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, h, ref } from 'vue'
import { Button, Dropdown, Tooltip, dayjsLocal } from 'frappe-ui'
import DropdownMoreOptions from '@/components/DropdownMoreOptions.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import type { DirectMessage } from '@/data/messages'
import { currentQuickReactionEmojis } from '@/data/reactionPreferences'
import { useSessionUser, useUser } from '@/data/users'
import { copyToClipboard } from '@/utils'
import { isImageEmoji } from '@/utils/emoji'
import { useIsMobile } from '@/utils/useIsMobile'
import MessageReactions from './MessageReactions.vue'
import { downloadFile, fileIcon, formatBytes, messageFiles, toFile } from './messageFiles'

const QUICK_REACTIONS = 6
const FULL_TIME = 'D MMM YYYY [at] h:mm A'

const props = defineProps<{
  message: DirectMessage
  mine: boolean
  last: boolean
  highlighted?: boolean
  seenAt?: string | null
  sender?: string
}>()

const emit = defineEmits<{
  edit: []
  delete: []
  reply: []
  react: [emoji: string]
  jump: [message: number]
  preview: [url: string]
}>()

const isMobile = useIsMobile()
const sessionUser = useSessionUser()

function authorName(user: string) {
  return user === sessionUser.name ? 'You' : useUser(user).full_name
}
const at = computed(() => dayjsLocal(props.message.creation))
const seen = computed(() => (props.seenAt ? dayjsLocal(props.seenAt) : null))
const seenShort = computed(() =>
  seen.value?.isSame(dayjsLocal(), 'day')
    ? seen.value.format('h:mm A')
    : seen.value?.format('D MMM'),
)
const edited = computed(() => Boolean(props.message.edited_at && !props.message.deleted_at))
const showAllReactions = ref(false)
const hasReactions = computed(
  () => !props.message.deleted_at && Object.keys(props.message.reactions ?? {}).length > 0,
)

const reply = computed(() =>
  props.message.reply && !props.message.reply.deleted ? props.message.reply : null,
)

const files = computed(() => (props.message.deleted_at ? [] : messageFiles(props.message.content)))

const filesOnly = computed(() => {
  const content = props.message.content
  if (reply.value || !content?.includes('data-attachment')) return false
  const doc = new DOMParser().parseFromString(content, 'text/html')
  doc.querySelectorAll('a[data-attachment]').forEach((link) => link.remove())
  return !doc.body.textContent?.trim() && !doc.querySelector('img, video')
})

const hasMedia = computed(() => {
  const content = props.message.content
  if (reply.value || !/<(img|video)\b/.test(content || '')) return false
  const doc = new DOMParser().parseFromString(content, 'text/html')
  return Boolean(doc.querySelector('img:not([data-emoji]), video'))
})

const frosted = computed(() => hasMedia.value || filesOnly.value || Boolean(reply.value))

const mediaLayout =
  '[&>*]:!my-0 [&>*+:is(img,video)]:!mt-1 [&>img]:block [&>img]:h-auto [&>img]:w-full [&>img]:object-cover [&>video]:w-full [&>:not(img,video)]:px-2 [&>:not(img,video)]:py-0.5 [&>:is(img,video)]:!max-h-[max(20rem,40cqw)] [&>p:has(>a[data-attachment])]:!p-0 [&>*+p:has(>a[data-attachment])]:!mt-1 [&_a[data-attachment]]:!my-0 [&_a[data-attachment]]:!w-full'

const PREVIEWABLE = 'img:not([data-emoji]), a[data-attachment]'

function previewTarget(event: MouseEvent | PointerEvent) {
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return null
  return (event.target as HTMLElement).closest(PREVIEWABLE)
}

function onContentPointerdown(event: PointerEvent) {
  if (previewTarget(event)) event.stopPropagation()
}

function onContentClick(event: MouseEvent) {
  const target = previewTarget(event)
  if (!target) return
  event.preventDefault()
  event.stopPropagation()
  const file = toFile(target)
  if ((event.target as HTMLElement).closest('[data-download]')) downloadFile(file)
  else emit('preview', file.url)
}

const MEDIA = 'img:not([data-emoji]), video'

function liftMedia(doc: Document) {
  doc.body.querySelectorAll('p').forEach((paragraph) => {
    if (!paragraph.querySelector(`:scope > :is(${MEDIA})`)) return
    const parts: Node[] = []
    let text = doc.createElement('p')
    const flush = () => {
      if (text.textContent?.trim() || text.querySelector('img')) parts.push(text)
      text = doc.createElement('p')
    }
    for (const node of [...paragraph.childNodes]) {
      if (node instanceof Element && node.matches(MEDIA)) {
        flush()
        parts.push(node)
      } else {
        text.append(node)
      }
    }
    flush()
    paragraph.replaceWith(...parts)
  })
}

const html = computed(() => {
  const content = props.message.content
  if (!content?.includes('data-attachment') && !hasMedia.value) return content
  const doc = new DOMParser().parseFromString(content, 'text/html')
  if (hasMedia.value) liftMedia(doc)
  doc.querySelectorAll('a[data-attachment]').forEach((link) => {
    const name = link.getAttribute('data-file-name') || link.textContent || 'Attachment'
    const size = Number(link.getAttribute('data-file-size'))
    const span = (className: string, ...children: (Node | string)[]) => {
      const element = doc.createElement('span')
      element.className = className
      element.append(...children)
      return element
    }
    const download = span(
      'grid size-7 shrink-0 place-items-center rounded-5 text-ink-gray-6 hover:bg-surface-gray-3 hover:text-ink-gray-8',
      span('lucide-download size-4'),
    )
    download.setAttribute('data-download', '')
    download.setAttribute('role', 'button')
    download.setAttribute('aria-label', `Download ${name}`)
    link.className =
      'my-0.5 flex w-72 max-w-full items-center gap-2.5 rounded-7 border border-outline-gray-2 bg-surface-base py-2 pl-2 pr-1.5 no-underline transition-colors hover:bg-surface-gray-1'
    link.setAttribute('download', name)
    link.replaceChildren(
      span(
        'grid size-9 shrink-0 place-items-center rounded-5 bg-surface-gray-2',
        span(`${fileIcon(name)} size-5 text-ink-gray-6`),
      ),
      span(
        'min-w-0 flex-1 leading-tight',
        span('block truncate text-base-medium text-ink-gray-8', name),
        ...(size > 0 ? [span('mt-0.5 block text-sm text-ink-gray-5', formatBytes(size))] : []),
      ),
      download,
    )
  })
  return doc.body.innerHTML
})

function plainText(html: string) {
  const lines = html
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(p|li|h\d|blockquote|pre)>/gi, '$&\n')
  return new DOMParser().parseFromString(lines, 'text/html').body.textContent?.trim() ?? ''
}

function emojiButton(emoji: string, close: () => void) {
  return h(
    Button,
    {
      variant: 'ghost',
      size: 'sm',
      label: emoji,
      class: 'font-[emoji]',
      onClick: () => {
        emit('react', emoji)
        close()
      },
    },
    {
      icon: () =>
        isImageEmoji(emoji)
          ? h('img', { src: emoji, alt: '', class: 'size-4 object-contain' })
          : h('span', { class: 'text-md' }, emoji),
    },
  )
}

const actions = computed(() => {
  if (props.message.deleted_at) return []
  return [
    {
      label: 'React',
      onClick: (event: Event) => event.preventDefault(),
      slots: {
        item: ({ close }: { close: () => void }) =>
          h(
            'div',
            {
              class: [
                'gap-0.5 px-0.5 pb-1 outline-none',
                showAllReactions.value ? 'grid grid-cols-10' : 'flex items-center',
              ],
            },
            showAllReactions.value
              ? currentQuickReactionEmojis.value.map((emoji) => emojiButton(emoji, close))
              : [
                  ...currentQuickReactionEmojis.value
                    .slice(0, QUICK_REACTIONS)
                    .map((emoji) => emojiButton(emoji, close)),
                  h(Button, {
                    variant: 'ghost',
                    size: 'sm',
                    icon: 'lucide-smile-plus',
                    label: 'More reactions',
                    onClick: () => (showAllReactions.value = true),
                  }),
                ],
          ),
      },
    },
    { label: 'Reply', icon: 'lucide-reply', onClick: () => emit('reply') },
    ...(plainText(props.message.content)
      ? [
          {
            label: 'Copy',
            icon: 'lucide-copy',
            onClick: () => copyToClipboard(plainText(props.message.content)),
          },
        ]
      : []),
    ...(files.value.length
      ? [
          {
            label: files.value.length > 1 ? 'Download all' : 'Download',
            icon: 'lucide-download',
            onClick: () =>
              files.value.forEach((file, index) =>
                setTimeout(() => downloadFile(file), index * 300),
              ),
          },
        ]
      : []),
    ...(props.mine
      ? [
          { label: 'Edit', icon: 'lucide-pen-line', onClick: () => emit('edit') },
          {
            label: 'Delete',
            icon: 'lucide-trash-2',
            theme: 'red' as const,
            onClick: () => emit('delete'),
          },
        ]
      : []),
  ]
})
const menuOpen = ref(false)
const menu = computed(() => ({
  options: actions.value,
  align: props.mine ? ('end' as const) : ('start' as const),
  open: menuOpen.value,
  'onUpdate:open': (open: boolean) => {
    menuOpen.value = open
    if (!open) showAllReactions.value = false
  },
}))
const tapForActions = computed(() => isMobile.value && actions.value.length > 0)
const hoverActions = computed(() => !isMobile.value && actions.value.length > 0)

function opensMenu(event: MouseEvent) {
  return hoverActions.value && !(event.target as HTMLElement).closest('a, img, video, button')
}

function onDoubleClick(event: MouseEvent) {
  if (!opensMenu(event)) return
  window.getSelection()?.removeAllRanges()
  menuOpen.value = true
}

function onContextMenu(event: MouseEvent) {
  if (!opensMenu(event)) return
  event.preventDefault()
  menuOpen.value = true
}

const footer = computed(() =>
  [edited.value && 'Edited', props.last && at.value.format('h:mm A')].filter(Boolean).join(' · '),
)
</script>
