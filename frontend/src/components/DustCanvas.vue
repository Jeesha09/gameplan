<template>
  <canvas ref="canvas" class="censor-dust-canvas" aria-hidden="true" />
</template>
<script setup lang="ts">
import { onBeforeUnmount, onMounted, useTemplateRef } from 'vue'
import { startDust } from '@/utils/censorDust'

// Dust over the censored word this canvas sits in.
const canvas = useTemplateRef<HTMLCanvasElement>('canvas')
let stop = () => {}
onMounted(() => {
  if (canvas.value) stop = startDust(canvas.value, () => canvas.value?.parentElement ?? null)
})
onBeforeUnmount(() => stop())
</script>
