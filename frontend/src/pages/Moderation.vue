<template>
  <PageHeaderMobile class="sm:hidden" title="Moderation">
    <template #prefix><PageHeaderBackButton :fallback-route="{ name: 'More' }" /></template>
  </PageHeaderMobile>
  <PageHeader class="hidden sm:flex">
    <Breadcrumbs :items="[{ label: 'Moderation', route: { name: 'Moderation' } }]" />
  </PageHeader>
  <div class="flex min-h-0 flex-1 flex-col text-ink-gray-9">
    <CommunityModeration
      v-if="selected || siteWide"
      :key="selected"
      :community-id="selected"
      :site-wide="siteWide"
      @community="openCommunitySection"
    >
      <template #sidebar
        ><Select v-model="selected" label="Community" :options="options"
      /></template>
      <template v-if="isGlobalAdmin(useSessionUser())" #administration>
        <SidebarLabel class="mt-6">Site administration</SidebarLabel>
        <SidebarItem
          label="Account suspensions"
          icon="lucide-shield-ban"
          :active="siteWide && siteSection === 'suspensions'"
          class="mt-0.5"
          @click="openAccountSuspensions"
        />
        <SidebarItem
          label="Posting limits"
          icon="lucide-gauge"
          :active="siteWide && siteSection === 'posting-limits'"
          class="mt-0.5"
          @click="openPostingLimits"
        />
      </template>
      <template #site-wide>
        <PostingLimits v-if="siteSection === 'posting-limits'" />
        <AccountSuspensions v-else />
      </template>
    </CommunityModeration>
    <p v-else class="py-12 text-center text-base text-ink-gray-6">
      Only Community moderators can open this page.
    </p>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Breadcrumbs,
  PageHeader,
  PageHeaderBackButton,
  PageHeaderMobile,
  SidebarItem,
  SidebarLabel,
  Select,
} from 'frappe-ui'
import { communities } from '@/data/communities'
import { useSessionUser } from '@/data/users'
import { canModerateCommunity, isGlobalAdmin } from '@/utils/permissions'
import CommunityModeration from './CommunityModeration.vue'
import AccountSuspensions from '@/components/AccountSuspensions.vue'
import PostingLimits from '@/components/PostingLimits.vue'
const route = useRoute()
const router = useRouter()
const siteWide = computed(() => route.query.scope === 'site' && isGlobalAdmin(useSessionUser()))
const siteSection = computed(() =>
  route.query.tab === 'posting-limits' ? 'posting-limits' : 'suspensions',
)
function openCommunitySection(tab: string) {
  router.replace({ name: 'Moderation', query: { community: selected.value, tab } })
}
function openAccountSuspensions() {
  router.replace({ name: 'Moderation', query: { community: selected.value, scope: 'site' } })
}
function openPostingLimits() {
  router.replace({
    name: 'Moderation',
    query: { community: selected.value, scope: 'site', tab: 'posting-limits' },
  })
}
const options = computed(() =>
  (communities.data || [])
    .filter((community) => canModerateCommunity(community, useSessionUser()))
    .map((community) => ({ label: community.title, value: community.name })),
)
const selected = computed({
  get: () =>
    options.value.find((option) => option.value === route.query.community)?.value ||
    options.value[0]?.value ||
    '',
  set: (community) => router.replace({ name: 'Moderation', query: { community } }),
})
</script>
