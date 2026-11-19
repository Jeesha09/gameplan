<template>
  <div v-if="favorites.length" class="flex items-center gap-1" data-profile-badge-coins>
    <BadgeMedallion
      v-for="badge in favorites"
      :key="badge.name"
      size="sm"
      :family="badge.family"
      :tier="badge.tier"
      :title="badge.title"
      :description="badge.description"
      :granted-at="badge.granted_at"
      :count="badge.count"
    />
  </div>
</template>
<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { useCall } from 'frappe-ui'
import BadgeMedallion from './BadgeMedallion.vue'
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
