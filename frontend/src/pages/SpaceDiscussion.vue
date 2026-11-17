<template>
  <div class="flex flex-col" v-if="space">
    <p
      v-if="isCommunityBanned(space?.team, useSessionUser())"
      class="p-4 text-base text-ink-gray-5"
    >
      You cannot participate in this Community. You can still read accessible content.
    </p>
    <!-- Keyed so opening another discussion mounts a fresh view instead of reusing this one -->
    <DiscussionView
      :key="postId"
      class="w-full"
      :postId="postId"
      :read-only-mode="
        Boolean(space?.archived_at) ||
        readOnlyMode ||
        publicVisitor ||
        isCommunityBanned(space?.team, useSessionUser())
      "
    />
  </div>
  <SpaceUnavailable v-else :communityId="communityId" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { isCommunityBanned } from '@/utils/permissions'
import { useSessionUser } from '@/data/users'
import { readOnlyMode } from '@/data/readOnlyMode'
import DiscussionView from '@/components/DiscussionView.vue'
import SpaceUnavailable from '@/components/SpaceUnavailable.vue'
import { useSpace } from '@/data/spaces'
import { isPublicVisitor } from '@/utils/publicAccess'

interface Props {
  communityId: string
  spaceId: string
  postId: string
  slug?: string
}

const props = defineProps<Props>()
const space = useSpace(() => props.spaceId)
const publicVisitor = computed(() => isPublicVisitor())
</script>
