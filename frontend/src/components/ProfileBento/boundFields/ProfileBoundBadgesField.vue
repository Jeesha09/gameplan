<template>
  <p class="text-p-sm text-ink-gray-6" :data-profile-panel-field="spec.field">
    The badges you have earned, with your favourites first. Choose them with the star on the Badges
    tab of your profile.
  </p>
</template>

<script setup lang="ts">
import type { ProfileBoundFieldSpec, ProfileFieldDraft } from '../types'

// Takes the same props as the other editors, though a badge is earned and not typed in.
defineProps<{
  spec: ProfileBoundFieldSpec
  draft: ProfileFieldDraft
}>()
</script>
