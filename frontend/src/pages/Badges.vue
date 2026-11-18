<template>
  <PageHeaderMobile class="sm:hidden" title="Badges">
    <template #prefix>
      <PageHeaderBackButton :fallback-route="{ name: 'More' }" />
    </template>
  </PageHeaderMobile>
  <PageHeader class="hidden sm:flex">
    <Breadcrumbs class="h-7" :items="[{ label: 'Badges', route: { name: 'Badges' } }]" />
  </PageHeader>
  <div class="body-container pt-5 pb-40">
    <LoadError
      v-if="badges.error && !badges.data"
      :message="errorText(badges.error, 'Could not load badges.')"
      @retry="badges.reload()"
    />
    <EmptyStateBox
      v-else-if="badges.data && !badges.data.enabled"
      icon="lucide-award"
      title="Badges are off"
      description="A global admin can turn badges on in Site administration."
    />
    <template v-else-if="badges.data">
      <section v-for="group in groups" :key="group.title" class="mb-8">
        <h2 class="mb-2 text-lg font-semibold text-ink-gray-9">{{ group.title }}</h2>
        <div
          v-for="badge in group.badges"
          :key="badge.name"
          class="-mx-2 flex items-center gap-3 rounded-lg px-2 py-2.5 hover:bg-surface-gray-2"
        >
          <BadgeMedallion
            :family="badge.family"
            :tier="badge.tier"
            :title="badge.title"
            :description="badge.description"
          />
          <router-link
            :to="{ name: 'Badge', params: { badgeId: badge.name } }"
            class="flex min-w-0 flex-1 items-center gap-3 rounded focus-visible:focus-ring"
          >
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-1.5">
                <span class="text-base-medium text-ink-gray-9">{{ badge.title }}</span>
                <span
                  v-if="badge.held"
                  class="lucide-circle-check size-4 text-ink-gray-6"
                  aria-label="You have this badge"
                />
              </div>
              <p class="text-p-sm text-ink-gray-6">{{ badge.description }}</p>
            </div>
            <span class="shrink-0 text-p-sm text-ink-gray-6">
              {{ badge.holders }} {{ badge.holders === 1 ? 'person' : 'people' }}
            </span>
          </router-link>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  Breadcrumbs,
  PageHeader,
  PageHeaderBackButton,
  PageHeaderMobile,
  useCall,
  usePageMeta,
} from 'frappe-ui'
import BadgeMedallion from '@/components/Badges/BadgeMedallion.vue'
import EmptyStateBox from '@/components/EmptyStateBox.vue'
import LoadError from '@/components/LoadError.vue'
import { BADGE_GROUPS, type ListedBadge } from '@/data/badges'
import { errorText } from '@/utils'

usePageMeta(() => ({ title: 'Badges' }))

const badges = useCall<{ enabled: 0 | 1; badges: ListedBadge[] }>({
  url: '/api/v2/method/gameplan.badges.api.list_badges',
  cacheKey: 'badges',
})

const groups = computed(() =>
  BADGE_GROUPS.map((title) => ({
    title,
    badges: (badges.data?.badges || []).filter((badge) => badge.badge_group === title),
  })).filter((group) => group.badges.length),
)
</script>
