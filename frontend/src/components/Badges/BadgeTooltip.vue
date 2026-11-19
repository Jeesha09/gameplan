<template>
  <Tooltip :hover-delay="200" :disabled="disabled">
    <slot />
    <template #content>
      <div class="max-w-56 py-0.5">
        <div class="font-medium">
          {{ title }} · {{ tier }}<template v-if="count > 1"> · {{ count }} times</template>
        </div>
        <div v-if="description" class="mt-0.5 opacity-80">{{ description }}</div>
        <div v-if="grantedAt" class="mt-1 opacity-60">Earned {{ earned }}</div>
      </div>
    </template>
  </Tooltip>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { Tooltip, dayjsLocal } from 'frappe-ui'
import type { BadgeTier } from '@/data/badges'

const props = withDefaults(
  defineProps<{
    title: string
    tier: BadgeTier
    /** What the badge is for. */
    description?: string
    /** The latest grant, when the caller knows it. */
    grantedAt?: string
    count?: number
    /** Leaves the tooltip off where the page already says all of this. */
    disabled?: boolean
  }>(),
  { description: '', grantedAt: '', count: 1, disabled: false },
)

const earned = computed(() => dayjsLocal(props.grantedAt).format('D MMM YYYY'))
</script>
