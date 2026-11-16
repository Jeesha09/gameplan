<template>
  <p class="text-p-sm font-medium text-ink-gray-8">{{ progressHeading(progress) }}</p>
  <ul v-if="progress.requirements.length" class="mt-2 space-y-1.5">
    <li
      v-for="step in progress.requirements"
      :key="step.key"
      class="flex items-start gap-2 text-p-sm text-ink-gray-7"
    >
      <span
        :class="[
          step.met ? 'lucide-circle-check text-ink-gray-7' : 'lucide-circle text-ink-gray-4',
          'mt-0.5 size-4 shrink-0',
        ]"
        aria-hidden="true"
      />
      <span
        ><span class="sr-only">{{ step.met ? 'Met: ' : 'Not met: ' }}</span
        >{{ requirementLabel(step, progress) }}</span
      >
    </li>
  </ul>
  <p v-if="progress.locked" class="mt-2 text-p-sm text-ink-gray-6">
    This level is locked, so the rules do not change it.
  </p>
  <p v-else-if="graceUntil" class="mt-2 text-p-sm text-ink-gray-6">
    Rechecked from {{ graceUntil }}.
  </p>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { dayjsLocal } from 'frappe-ui'
import { progressHeading, requirementLabel, type LevelProgress } from '@/data/trustLevels'

const props = defineProps<{ progress: LevelProgress }>()
const graceUntil = computed(() =>
  props.progress.level === 3 && props.progress.grace_until
    ? dayjsLocal(props.progress.grace_until).format('D MMM YYYY')
    : '',
)
</script>
