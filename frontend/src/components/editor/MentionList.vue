<template>
  <div
    v-if="items.length"
    class="min-w-40 max-w-96 rounded-6 border border-outline-gray-2 bg-surface-elevation-2 p-1 text-base shadow-2xl"
  >
    <div
      v-for="(item, index) in items"
      :key="item.id"
      role="option"
      :aria-selected="index === selectedIndex"
      :class="[
        'flex w-full cursor-pointer items-center gap-2 whitespace-nowrap rounded-4 px-2 py-1.5 text-sm text-ink-gray-9',
        index === selectedIndex ? 'bg-surface-gray-2' : '',
      ]"
      @click="command(item)"
      @mouseover="selectedIndex = index"
    >
      <span
        v-if="item.id === '_everyone_'"
        class="lucide-users size-4 shrink-0 text-ink-gray-5"
        aria-hidden="true"
      />
      <UserAvatar v-else :user="item.id" size="xs" class="shrink-0" />
      <span class="truncate">{{ item.label }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import UserAvatar from '@/components/UserAvatar.vue'

export interface MentionItem {
  id: string
  label: string
  value: string
}

const props = defineProps<{
  items: MentionItem[]
  command: (item: MentionItem) => void
}>()

const selectedIndex = ref(0)

watch(
  () => props.items,
  () => {
    selectedIndex.value = 0
  },
)

function onKeyDown({ event }: { event: KeyboardEvent }) {
  const count = props.items.length
  if (!count) return false

  if (event.key === 'ArrowUp') {
    selectedIndex.value = (selectedIndex.value + count - 1) % count
  } else if (event.key === 'ArrowDown') {
    selectedIndex.value = (selectedIndex.value + 1) % count
  } else if (event.key === 'Enter' || event.key === 'Tab') {
    props.command(props.items[selectedIndex.value])
  } else {
    return false
  }
  return true
}

defineExpose({ onKeyDown })
</script>
