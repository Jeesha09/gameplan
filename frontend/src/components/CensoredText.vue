<template>
  <!-- One element, so a flex parent, such as a breadcrumb link, cannot trim the spaces
       around a censored word. -->
  <span>
    <template v-for="(part, index) in parts" :key="index">
      <span v-if="index % 2" class="censor-dust" aria-label="Censored"
        >{{ part }}<DustCanvas
      /></span>
      <template v-else>{{ part }}</template>
    </template>
  </span>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import DustCanvas from './DustCanvas.vue'

// Plain text, such as a title, with each censored run drawn as dust. The editor does the
// same for post content with `CensorDust`.
const props = defineProps<{ text?: string | null }>()

// Splitting on a captured group puts the censored runs at the odd indexes.
const parts = computed(() => (props.text || '').split(/(■+)/))
</script>
