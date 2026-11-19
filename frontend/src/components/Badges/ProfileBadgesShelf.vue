<template>
  <div v-if="shown.length" ref="row" class="flex min-w-0 items-center gap-2" data-profile-badges>
    <BadgeMedallion
      v-for="badge in shown"
      :key="badge.name"
      class="badge-shelf-coin"
      size="lg"
      :family="badge.family"
      :tier="badge.tier"
      :title="badge.title"
      :description="badge.description"
      :granted-at="badge.granted_at"
      :count="badge.count"
    />
    <router-link
      v-if="hidden"
      :to="{ name: 'PersonProfileBadges', params: { personId: route.params.personId } }"
      class="grid size-16 shrink-0 place-items-center rounded-full border border-dashed border-outline-gray-3 text-sm font-medium text-ink-gray-6 transition hover:border-outline-gray-4 hover:bg-surface-gray-2 focus-visible:focus-ring"
      :aria-label="`${hidden} more badges`"
      @click.stop
    >
      +{{ hidden }}
    </router-link>
  </div>
</template>
<script setup lang="ts">
import { computed, inject, ref, useTemplateRef } from 'vue'
import { useRoute } from 'vue-router'
import { useElementSize } from '@vueuse/core'
import { useCall } from 'frappe-ui'
import BadgeMedallion from './BadgeMedallion.vue'
import { badgesEnabled, profileUserKey, type HeldBadge } from '@/data/badges'
import { useSessionUser } from '@/data/users'
import { isAnonymousVisitor } from '@/utils/publicAccess'

type Result = { enabled: 0 | 1; badges: HeldBadge[] }

const COIN = 64
const GAP = 8

const route = useRoute()
// The profile page says whose badges these are. The customize page does not, and edits the
// signed-in user's own profile.
const profileUser = inject(profileUserKey, ref(''))
const sessionUser = useSessionUser()
const user = computed(() => {
  if (!badgesEnabled() || isAnonymousVisitor()) return ''
  return profileUser.value || sessionUser.name || ''
})

const result = useCall<Result, { user: string }>({
  url: '/api/v2/method/gameplan.badges.api.user_badges',
  params: () => ({ user: user.value }),
  refetch: true,
  immediate: Boolean(user.value),
})
// The server lists favourites first, so those lead.
const badges = computed(() => result.data?.badges || [])

// One row. A fixed-height card cannot grow, so what does not fit becomes "+N".
const row = useTemplateRef<HTMLElement>('row')
const { width } = useElementSize(row)
const fits = computed(() => Math.max(1, Math.floor((width.value + GAP) / (COIN + GAP))))
const shown = computed(() => {
  if (!width.value || badges.value.length <= fits.value) return badges.value
  return badges.value.slice(0, fits.value - 1)
})
const hidden = computed(() => badges.value.length - shown.value.length)
</script>
