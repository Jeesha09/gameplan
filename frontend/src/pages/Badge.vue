<template>
  <PageHeaderMobile class="sm:hidden" :title="badge?.title || 'Badge'">
    <template #prefix>
      <PageHeaderBackButton :fallback-route="{ name: 'Badges' }" />
    </template>
  </PageHeaderMobile>
  <PageHeader class="hidden sm:flex">
    <Breadcrumbs
      class="h-7"
      :items="[
        { label: 'Badges', route: { name: 'Badges' } },
        { label: badge?.title || 'Badge', route: { name: 'Badge', params: { badgeId } } },
      ]"
    />
  </PageHeader>
  <div class="body-container pt-5 pb-40">
    <NotFound
      v-if="notFound"
      title="Badge not found"
      description="Badges may be off, or the link is wrong."
    />
    <LoadError
      v-else-if="holders.error && !badge"
      :message="errorText(holders.error, 'Could not load this badge.')"
      @retry="reload"
    />
    <template v-else-if="badge">
      <div class="flex items-center gap-4">
        <BadgeMedallion
          :family="badge.family"
          :tier="badge.tier"
          :title="badge.title"
          :description="badge.description"
          size="lg"
        />
        <div>
          <h1 class="text-2xl font-semibold text-ink-gray-9">{{ badge.title }}</h1>
          <p class="mt-1 text-p-base text-ink-gray-7">{{ badge.description }}</p>
          <p class="mt-0.5 text-p-sm text-ink-gray-6">{{ badge.tier }} · {{ badge.badge_group }}</p>
        </div>
      </div>
      <h2 class="mb-1 mt-8 text-base-medium text-ink-gray-8">Earned by</h2>
      <EmptyStateBox
        v-if="!rows.length"
        icon="lucide-award"
        title="Nobody yet"
        description="The first person to earn it shows up here."
      />
      <div
        v-for="row in rows"
        :key="row.name"
        class="flex items-center gap-3 border-b border-outline-gray-1 py-2.5"
      >
        <UserAvatarWithHover :user="row.user" size="lg" />
        <div class="min-w-0 flex-1">
          <UserProfileLink
            :user="row.user"
            class="text-base-medium text-ink-gray-9 hover:underline"
            >{{ useUser(row.user).full_name }}</UserProfileLink
          >
          <router-link
            v-if="row.post"
            class="block truncate text-p-sm text-ink-gray-6 hover:underline"
            :to="postRoute(row.post)"
            >{{ row.post.title }}</router-link
          >
        </div>
        <span class="shrink-0 text-p-sm text-ink-gray-6" :title="fullTimestamp(row.granted_at)">
          {{ dayjsLocal(row.granted_at).fromNow() }}
        </span>
      </div>
      <Button v-if="cursor" class="mt-3" :loading="holders.loading" @click="more">Show more</Button>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  Breadcrumbs,
  Button,
  PageHeader,
  PageHeaderBackButton,
  PageHeaderMobile,
  dayjsLocal,
  useCall,
  usePageMeta,
} from 'frappe-ui'
import BadgeMedallion from '@/components/Badges/BadgeMedallion.vue'
import EmptyStateBox from '@/components/EmptyStateBox.vue'
import LoadError from '@/components/LoadError.vue'
import UserAvatarWithHover from '@/components/UserAvatarWithHover.vue'
import UserProfileLink from '@/components/UserProfileLink.vue'
import NotFound from '@/pages/NotFound.vue'
import type { Badge, BadgeHolder } from '@/data/badges'
import { useUser } from '@/data/users'
import { errorText, fullTimestamp } from '@/utils'

const props = defineProps<{ badgeId: string }>()

type Page = { badge: Badge; holders: BadgeHolder[]; next_cursor: string }

const badge = ref<Badge | null>(null)
const rows = ref<BadgeHolder[]>([])
const cursor = ref('')
const notFound = ref(false)

const holders = useCall<Page, { badge: string; before: string }>({
  url: '/api/v2/method/gameplan.badges.api.badge_holders',
  immediate: false,
  onSuccess(page) {
    badge.value = page.badge
    rows.value = cursor.value ? [...rows.value, ...page.holders] : page.holders
    cursor.value = page.next_cursor
  },
  onError(error) {
    notFound.value = errorText(error, '').includes('not found')
  },
})

usePageMeta(() => ({ title: badge.value?.title || 'Badge' }))

function reload() {
  badge.value = null
  rows.value = []
  cursor.value = ''
  notFound.value = false
  holders.submit({ badge: props.badgeId, before: '' })
}

function more() {
  holders.submit({ badge: props.badgeId, before: cursor.value })
}

watch(() => props.badgeId, reload, { immediate: true })

function postRoute(post: NonNullable<BadgeHolder['post']>) {
  // The short route finds the Community from the Space.
  return {
    path: `/space/${post.space}/discussion/${post.discussion}`,
    query: post.doctype === 'GP Comment' ? { comment: post.name } : {},
  }
}
</script>
