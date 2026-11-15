<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition-opacity duration-150 ease-in-out"
      leave-active-class="transition-opacity duration-150 ease-in-out"
      enter-from-class="opacity-0"
      leave-to-class="opacity-0"
      appear
    >
      <div
        v-if="file"
        ref="viewer"
        tabindex="-1"
        class="fixed inset-0 z-50 flex flex-col bg-black text-white outline-none sm:bg-black/90"
        role="dialog"
        aria-modal="true"
        :aria-label="file.name"
      >
        <header class="grid grid-cols-[1fr_auto_1fr] items-center gap-3 p-4">
          <div class="flex min-w-0 items-center gap-2.5">
            <UserAvatar :user="file.owner" size="lg" class="hidden shrink-0 sm:block" />
            <div class="hidden min-w-0 sm:block">
              <div class="truncate text-base-medium">{{ author }}</div>
              <div class="mt-0.5 text-sm text-gray-400">{{ sentAt }}</div>
            </div>
          </div>

          <div class="flex items-center gap-3">
            <div v-if="files.length > 1" :class="group">
              <Tooltip text="Previous">
                <button
                  :class="[control, 'rounded-l-4']"
                  aria-label="Previous file"
                  :disabled="index === 0"
                  @click="go(-1)"
                >
                  <span class="lucide-chevron-left size-4" />
                </button>
              </Tooltip>
              <span class="select-none px-2 text-sm tabular-nums text-gray-400">
                {{ index + 1 }}/{{ files.length }}
              </span>
              <Tooltip text="Next">
                <button
                  :class="[control, 'rounded-r-4']"
                  aria-label="Next file"
                  :disabled="index === files.length - 1"
                  @click="go(1)"
                >
                  <span class="lucide-chevron-right size-4" />
                </button>
              </Tooltip>
            </div>

            <div v-if="file.kind === 'image'" :class="[group, 'hidden sm:flex']">
              <Tooltip text="Zoom out">
                <button :class="[control, 'rounded-l-4']" aria-label="Zoom out" @click="zoomBy(-1)">
                  <span class="lucide-minus size-4" />
                </button>
              </Tooltip>
              <Tooltip text="Reset zoom">
                <button :class="[control, 'text-sm text-gray-400']" @click="zoom = 100">
                  {{ zoom }}%
                </button>
              </Tooltip>
              <Tooltip text="Zoom in">
                <button :class="[control, 'rounded-r-4']" aria-label="Zoom in" @click="zoomBy(1)">
                  <span class="lucide-plus size-4" />
                </button>
              </Tooltip>
            </div>

            <div :class="group">
              <Tooltip text="Download">
                <button
                  :class="[control, 'rounded-l-4', !canShare && 'max-sm:rounded-r-4']"
                  aria-label="Download"
                  @click="downloadFile(file)"
                >
                  <span class="lucide-download size-4" />
                </button>
              </Tooltip>
              <Tooltip v-if="canShare" text="Share">
                <button :class="[control, 'max-sm:rounded-r-4']" aria-label="Share" @click="share">
                  <span class="lucide-share-2 size-4" />
                </button>
              </Tooltip>
              <Tooltip :text="isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'">
                <button
                  :class="[control, 'hidden rounded-r-4 sm:block']"
                  :aria-label="isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'"
                  @click="toggleFullscreen"
                >
                  <span
                    :class="isFullscreen ? 'lucide-minimize' : 'lucide-maximize'"
                    class="size-4"
                  />
                </button>
              </Tooltip>
            </div>
          </div>

          <div class="flex justify-end">
            <div :class="group">
              <Tooltip text="Close">
                <button :class="[control, 'rounded-4']" aria-label="Close" @click="emit('close')">
                  <span class="lucide-x size-4" />
                </button>
              </Tooltip>
            </div>
          </div>
        </header>

        <div
          ref="stage"
          class="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden px-3 sm:px-16"
          @click.self="emit('close')"
        >
          <img
            v-if="file.kind === 'image'"
            :key="file.url"
            :src="file.url"
            :alt="file.name"
            class="max-h-full max-w-full rounded-5 object-contain transition-transform duration-150"
            :style="{ transform: `scale(${zoom / 100})` }"
          />
          <video
            v-else-if="file.kind === 'video'"
            :key="file.url"
            :src="file.url"
            controls
            autoplay
            class="max-h-full max-w-full rounded-5"
          />
          <iframe
            v-else-if="file.kind === 'pdf'"
            :key="file.url"
            :src="file.url"
            :title="file.name"
            class="h-full w-full max-w-5xl rounded-5 bg-white"
          />
          <div
            v-else
            class="flex w-80 max-w-full flex-col items-center rounded-7 bg-gray-900 px-6 py-8 text-center"
          >
            <div class="grid size-16 place-items-center rounded-6 bg-white/10">
              <span :class="[fileIcon(file.name), 'size-8 text-gray-200']" aria-hidden="true" />
            </div>
            <div class="mt-4 text-sm text-gray-400">No preview available</div>
            <button
              class="mt-4 rounded-6 bg-white px-3 py-1.5 text-base-medium text-gray-900 transition-colors hover:bg-gray-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/40"
              @click="downloadFile(file)"
            >
              Download
            </button>
          </div>
        </div>

        <footer class="flex items-center justify-center gap-2 px-4 pb-5 pt-3">
          <span class="truncate text-base-medium">{{ file.name }}</span>
          <span
            v-if="file.size"
            class="shrink-0 rounded-full bg-white/10 px-2 py-0.5 text-xs text-gray-300"
          >
            {{ formatBytes(file.size) }}
          </span>
        </footer>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, useTemplateRef, watch } from 'vue'
import { useEventListener, useFullscreen } from '@vueuse/core'
import { Tooltip, dayjsLocal, toast } from 'frappe-ui'
import UserAvatar from '@/components/UserAvatar.vue'
import { useSessionUser, useUser } from '@/data/users'
import { downloadFile, fileIcon, formatBytes, type ViewerFile } from './messageFiles'

const ZOOM_STEP = 25
const MIN_ZOOM = 25
const MAX_ZOOM = 300

const props = defineProps<{
  files: ViewerFile[]
  start: number
}>()

const emit = defineEmits<{ close: [] }>()

const group = 'flex items-center rounded-4 bg-black/65'
const control =
  'p-2 text-white transition-colors hover:bg-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/40 disabled:opacity-40 disabled:hover:bg-transparent'

const sessionUser = useSessionUser()
const viewer = useTemplateRef<HTMLElement>('viewer')
const { isFullscreen, toggle: toggleFullscreen } = useFullscreen(viewer)
const index = ref(Math.max(0, props.start))
const zoom = ref(100)
const file = computed(() => props.files[index.value])
const author = computed(() =>
  file.value.owner === sessionUser.name ? 'You' : useUser(file.value.owner).full_name,
)
const sentAt = computed(() => dayjsLocal(file.value.creation).format('D MMM YYYY, h:mm A'))
const canShare = typeof navigator !== 'undefined' && 'share' in navigator && 'canShare' in navigator

watch(index, () => (zoom.value = 100))

function go(step: number) {
  index.value = Math.min(Math.max(index.value + step, 0), props.files.length - 1)
}

function setZoom(value: number) {
  zoom.value = Math.round(Math.min(Math.max(value, MIN_ZOOM), MAX_ZOOM))
}

function zoomBy(direction: number) {
  setZoom(zoom.value + direction * ZOOM_STEP)
}

const stage = useTemplateRef<HTMLElement>('stage')
let pinchStart = 0
let pinchZoom = 100

function distance(touches: TouchList) {
  return Math.hypot(
    touches[1].clientX - touches[0].clientX,
    touches[1].clientY - touches[0].clientY,
  )
}

useEventListener(
  stage,
  'wheel',
  (event: WheelEvent) => {
    if (file.value.kind !== 'image') return
    event.preventDefault()
    const change = -event.deltaY * (event.ctrlKey ? 0.5 : 0.2)
    let next = zoom.value + change
    const crossesFit = (zoom.value - 100) * (next - 100) < 0
    if (crossesFit && Math.abs(next - 100) < Math.abs(change) * 1.5) next = 100
    setZoom(next)
  },
  { passive: false },
)

useEventListener(
  stage,
  'touchstart',
  (event: TouchEvent) => {
    if (event.touches.length !== 2 || file.value.kind !== 'image') return
    pinchStart = distance(event.touches)
    pinchZoom = zoom.value
  },
  { passive: true },
)

useEventListener(
  stage,
  'touchmove',
  (event: TouchEvent) => {
    if (event.touches.length !== 2 || !pinchStart) return
    event.preventDefault()
    setZoom((pinchZoom * distance(event.touches)) / pinchStart)
  },
  { passive: false },
)

useEventListener(stage, 'touchend', () => (pinchStart = 0))

async function share() {
  const current = file.value
  try {
    const blob = await (await fetch(current.url)).blob()
    const shared = new File([blob], current.name, { type: blob.type })
    if (!navigator.canShare({ files: [shared] })) {
      toast.error("This file can't be shared from this browser")
      return
    }
    await navigator.share({ files: [shared], title: current.name })
  } catch (error) {
    if ((error as DOMException)?.name !== 'AbortError') toast.error('Could not share this file')
  }
}

useEventListener(window, 'keydown', (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    if (isFullscreen.value) return
    event.preventDefault()
    event.stopPropagation()
    emit('close')
  } else if (event.key === 'ArrowLeft') go(-1)
  else if (event.key === 'ArrowRight') go(1)
})

onMounted(() => viewer.value?.focus())
</script>
