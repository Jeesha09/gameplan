<template>
  <div class="pb-16">
    <LoadError
      v-if="badges.error && !badges.data"
      :message="errorText(badges.error, 'Could not load badges.')"
      @retry="badges.reload()"
    />
    <template v-else-if="badges.data">
      <EmptyStateBox
        v-if="!held.length"
        icon="lucide-award"
        title="No badges yet"
        :description="
          isOwnProfile
            ? 'Badges come from taking part. See which ones you can earn.'
            : 'Badges they earn show up here.'
        "
      />
      <p v-if="isOwnProfile && held.length" class="mb-3 text-p-sm text-ink-gray-6">
        Star up to {{ MAX_FAVORITES }} badges to show them on your profile and hover card.
      </p>
      <div class="grid gap-2 sm:grid-cols-2">
        <div
          v-for="badge in held"
          :key="badge.name"
          class="flex items-center gap-3 rounded-lg border border-outline-gray-1 px-3 py-2.5"
        >
          <BadgeMedallion
            :family="badge.family"
            :tier="badge.tier"
            :title="badge.title"
            :description="badge.description"
            :granted-at="badge.granted_at"
            :count="badge.count"
          />
          <component
            :is="isAdmin ? 'router-link' : 'div'"
            v-bind="isAdmin ? { to: { name: 'Badge', params: { badgeId: badge.name } } } : {}"
            class="min-w-0 flex-1"
            :class="{ 'hover:underline': isAdmin }"
          >
            <div class="text-base-medium text-ink-gray-9">
              {{ badge.title
              }}<span v-if="badge.count > 1" class="text-ink-gray-6"> × {{ badge.count }}</span>
            </div>
            <div class="truncate text-p-sm text-ink-gray-6">{{ badge.description }}</div>
          </component>
          <Button
            v-if="isOwnProfile"
            variant="ghost"
            :icon="badge.is_favorite ? 'lucide-star-off' : 'lucide-star'"
            :label="badge.is_favorite ? `Unstar ${badge.title}` : `Star ${badge.title}`"
            :tooltip="badge.is_favorite ? 'Remove from favourites' : 'Show first'"
            :disabled="!badge.is_favorite && favorites.length >= MAX_FAVORITES"
            :loading="saving === badge.name"
            @click="toggleFavorite(badge)"
          />
          <span
            v-else-if="badge.is_favorite"
            class="lucide-star size-4 text-ink-gray-5"
            aria-label="Favourite"
          />
        </div>
      </div>
      <Button class="mt-4" variant="ghost" icon-left="lucide-award" :route="{ name: 'Badges' }">
        All badges
      </Button>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button, call, toast, useCall } from 'frappe-ui'
import BadgeMedallion from '@/components/Badges/BadgeMedallion.vue'
import EmptyStateBox from '@/components/EmptyStateBox.vue'
import LoadError from '@/components/LoadError.vue'
import { MAX_FAVORITES, type HeldBadge } from '@/data/badges'
import { useSessionUser } from '@/data/users'
import type { GPUserProfile } from '@/types/doctypes'
import { errorText } from '@/utils'
import { isGlobalAdmin } from '@/utils/permissions'

defineOptions({ name: 'PersonProfileBadges' })

const props = defineProps<{
  profile: { doc?: GPUserProfile | null }
  personId: string
}>()

type Result = { enabled: 0 | 1; badges: HeldBadge[] }

const user = computed(() => props.profile.doc?.user || '')
const isAdmin = isGlobalAdmin(useSessionUser())
const isOwnProfile = computed(() => user.value === useSessionUser().name)
const badges = useCall<Result, { user: string }>({
  url: '/api/v2/method/gameplan.badges.api.user_badges',
  params: () => ({ user: user.value }),
  refetch: true,
  immediate: Boolean(user.value),
})
const held = computed(() => badges.data?.badges || [])
const favorites = computed(() => held.value.filter((badge) => badge.is_favorite))
const saving = ref('')

async function toggleFavorite(badge: HeldBadge) {
  const names = favorites.value.map((favorite) => favorite.name)
  const next = badge.is_favorite
    ? names.filter((name) => name !== badge.name)
    : [...names, badge.name]
  saving.value = badge.name
  try {
    await call('gameplan.badges.api.set_favorites', { badges: next })
    await badges.reload()
  } catch (error) {
    toast.error(errorText(error, 'Could not save your favourite badges.'))
  } finally {
    saving.value = ''
  }
}
</script>
