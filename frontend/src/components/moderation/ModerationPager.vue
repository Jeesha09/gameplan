<template>
  <div v-if="previous || next" class="flex justify-end gap-1 pt-3">
    <Button
      variant="ghost"
      :disabled="!previous"
      icon-left="lucide-chevron-left"
      @click="$emit('previous')"
      >Previous</Button
    >
    <Button
      variant="ghost"
      :disabled="!next"
      icon-right="lucide-chevron-right"
      @click="$emit('next')"
      >Next</Button
    >
  </div>
</template>
<script setup lang="ts">
import { Button } from 'frappe-ui'

defineProps<{ previous?: boolean; next?: boolean }>()
defineEmits<{ previous: []; next: [] }>()
</script>
