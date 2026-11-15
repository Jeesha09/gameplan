<template>
  <UserAvatar v-if="people.length < 2" :user="people[0]" :size="size" v-bind="$attrs" />
  <div v-else class="relative" :class="layout.box" v-bind="$attrs">
    <span class="absolute left-0 top-0 flex">
      <UserAvatar :user="people[0]" :size="layout.inner" />
    </span>
    <span class="absolute bottom-0 right-0 flex">
      <UserAvatar :user="people[1]" :size="layout.inner" />
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import UserAvatar from '@/components/UserAvatar.vue'

defineOptions({ inheritAttrs: false })

const props = defineProps<{
  people: string[]
  size: 'sm' | 'md' | 'xl' | '3xl'
}>()

const LAYOUTS = {
  sm: { box: 'size-5', inner: 'xs' },
  md: { box: 'size-6', inner: 'xs' },
  xl: { box: 'size-8', inner: 'sm' },
  '3xl': { box: 'size-11.5', inner: 'xl' },
} as const

const layout = computed(() => LAYOUTS[props.size])
</script>
