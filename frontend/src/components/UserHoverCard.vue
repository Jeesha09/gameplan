<template>
  <slot v-if="userData.name == '_everyone_' || isAnonymous" />
  <HoverCard v-else v-model:open="userCardOpen" side="top" align="center" arrow>
    <template #trigger>
      <slot />
    </template>
    <template #default>
      <!-- panel shell (bg, radius, shadow) is provided by HoverCard -->
      <div class="w-64 p-3">
        <div class="flex items-center gap-2.5">
          <div>
            <div class="text-base-medium text-ink-gray-8">
              {{ userData.full_name }}
            </div>
          </div>
        </div>
        <div class="mt-0.5 text-p-sm text-ink-gray-6">{{ userData.bio }}</div>
        <!-- Only the coins: the tooltip on each names the badge. -->
        <div v-if="userData.favorite_badges?.length" class="mt-2 flex items-center gap-1.5">
          <BadgeMedallion
            v-for="badge in userData.favorite_badges"
            :key="badge.name"
            size="sm"
            :family="badge.family"
            :tier="badge.tier"
            :title="badge.title"
            :description="badge.description"
          />
        </div>
        <div class="text-p-xs text-ink-gray-6 mt-2">
          {{ userData.discussions_count_3m }}
          {{ pluralize(userData.discussions_count_3m, 'post', 'posts') }},
          {{ userData.comments_count_3m }}
          {{ pluralize(userData.comments_count_3m, 'reply', 'replies') }} in the last 3 months
        </div>
      </div>
    </template>
  </HoverCard>
</template>

<script setup lang="ts">
import { useUser } from '@/data/users'
import BadgeMedallion from './Badges/BadgeMedallion.vue'
import { HoverCard } from 'frappe-ui'
import { computed, ref } from 'vue'
import { isAnonymousVisitor } from '@/utils/publicAccess'

defineOptions({
  inheritAttrs: false,
})

const props = defineProps({
  user: {
    type: String,
    required: true,
  },
})

const isAnonymous = computed(() => isAnonymousVisitor())
const userData = useUser(props.user)

function pluralize(count: number, singular: string, plural: string) {
  return count === 1 ? singular : plural
}

const userCardOpen = ref(false)
</script>
