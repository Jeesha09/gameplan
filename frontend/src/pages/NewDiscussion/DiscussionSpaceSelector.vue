<template>
  <Combobox
    trigger="button"
    :options="spaceOptions"
    v-model="selectedSpace"
    placeholder="Select Space"
    :disabled="!isComposerEditable"
    @change="handleSpaceChange"
  >
    <template v-if="crumb" #trigger="{ disabled }">
      <button
        type="button"
        :disabled="disabled"
        class="flex min-w-0 items-center rounded-4 px-0.5 py-1 text-lg-medium text-ink-gray-5 hover:text-ink-gray-7"
      >
        <template v-if="crumbSpace">
          <template v-if="crumbCommunity">
            <span class="truncate">{{ crumbCommunity }}</span>
            <span class="mx-0.5 text-base text-ink-gray-4" aria-hidden="true">/</span>
          </template>
          <span class="truncate">{{ crumbSpace }}</span>
        </template>
        <span v-else class="truncate">Select Space</span>
        <span class="lucide-chevron-down ml-0.5 size-4 shrink-0" aria-hidden="true" />
      </button>
    </template>
    <template #item-prefix="{ item }">
      <SpaceIcon :icon="optionIcon(item)" class="size-4 text-ink-gray-6" />
    </template>
  </Combobox>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Combobox } from 'frappe-ui'
import SpaceIcon from '@/components/SpaceIcon.vue'
import { getCommunity } from '@/data/communities'
import { getSpace } from '@/data/spaces'
import { useNewDiscussionContext } from './useNewDiscussion'

defineProps<{ crumb?: boolean }>()

const { selectedSpace, spaceOptions, isComposerEditable, handleSpaceChange } =
  useNewDiscussionContext()

const space = computed(() => (selectedSpace.value ? getSpace(selectedSpace.value) : null))
const crumbSpace = computed(() => space.value?.title)
const crumbCommunity = computed(() =>
  space.value?.team ? getCommunity(space.value.team)?.title : null,
)

function optionIcon(item: unknown) {
  if (!item || typeof item !== 'object' || !('icon' in item)) return null
  return (item as { icon?: string | null }).icon || null
}
</script>
