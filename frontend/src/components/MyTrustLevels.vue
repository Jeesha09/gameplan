<template>
  <section v-if="progress" class="mb-5 mt-5" data-testid="my-trust-level">
    <h2 class="text-base font-medium text-ink-gray-9">Your level</h2>
    <div class="mt-2 rounded-5 border border-outline-gray-1 px-4 py-3">
      <div class="flex items-center justify-between gap-3">
        <p class="text-base text-ink-gray-9">{{ LEVEL_NAMES[progress.level] }}</p>
        <Badge :label="`Level ${progress.level}`" />
      </div>
      <p class="mb-3 mt-1 text-p-sm text-ink-gray-6">{{ levelDescriptions[progress.level] }}</p>
      <TrustRequirements :progress="progress" />
    </div>
  </section>
</template>
<script setup lang="ts">
import { Badge, useCall } from 'frappe-ui'
import { computed } from 'vue'
import TrustRequirements from '@/components/TrustRequirements.vue'
import { LEVEL_NAMES, levelDescriptions, type LevelProgress } from '@/data/trustLevels'

// POST: the first read can store the member's level, and a GET would discard it.
const request = useCall<({ enabled: 1 } & LevelProgress) | { enabled: 0 }>({
  url: '/api/v2/method/gameplan.trust_levels.my_level',
  method: 'POST',
  immediate: true,
})
const progress = computed(() => {
  const data = request.data
  return data && data.enabled ? (data as LevelProgress) : null
})
</script>
