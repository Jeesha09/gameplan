<template>
  <div v-if="favorites.length" class="flex items-start gap-1" data-profile-badge-ribbons>
    <BadgeRibbon v-for="badge in favorites" :key="badge.name" :badge="badge" />
  </div>
</template>
<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { useCall } from 'frappe-ui'
import BadgeRibbon from './BadgeRibbon.vue'
import { badgesEnabled, MAX_FAVORITES, profileUserKey, type HeldBadge } from '@/data/badges'
import { isAnonymousVisitor } from '@/utils/publicAccess'

type Result = { enabled: 0 | 1; badges: HeldBadge[] }

// Empty outside a profile page, such as on the customize page, and for visitors who are not
// signed in, who cannot read badges.
const profileUser = inject(profileUserKey, ref(''))
const user = computed(() => (badgesEnabled() && !isAnonymousVisitor() ? profileUser.value : ''))

const badges = useCall<Result, { user: string }>({
  url: '/api/v2/method/gameplan.badges.api.user_badges',
  params: () => ({ user: user.value }),
  refetch: true,
  immediate: Boolean(user.value),
})
// The server sorts favourites first and allows three.
const favorites = computed(() =>
  (badges.data?.badges || []).filter((badge) => badge.is_favorite).slice(0, MAX_FAVORITES),
)
</script>
