<template>
  <div class="flex flex-col items-center py-16 text-center">
    <div class="flex size-10 items-center justify-center rounded-full bg-surface-gray-2">
      <span :class="[icon, 'size-5 text-ink-gray-6']" aria-hidden="true" />
    </div>
    <p class="mt-3 text-base font-medium text-ink-gray-9">{{ title }}</p>
    <p v-if="description" class="mt-1 max-w-sm text-p-sm text-ink-gray-6">{{ description }}</p>
  </div>
</template>
<script setup lang="ts">
defineProps<{ icon: string; title: string; description?: string }>()
</script>
