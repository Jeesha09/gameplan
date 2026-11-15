<template>
  <ReactionsUI
    :reactions-count="reactionsCount"
    :toggle-reaction="toggleReaction"
    :tool-tip-text="toolTipText"
    :standard-emojis="currentQuickReactionEmojis"
    hide-picker
  />
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import type { ReactionCount } from '@/data/reactions'
import { currentQuickReactionEmojis } from '@/data/reactionPreferences'
import { useSessionUser, useUser } from '@/data/users'
import { useIsMobile } from '@/utils/useIsMobile'

const props = defineProps<{
  reactions: Record<string, string[]>
  toggleReaction: (emoji: string) => void
}>()

const isMobile = useIsMobile()
const ReactionsMobile = defineAsyncComponent(() => import('@/components/ReactionsMobile.vue'))
const ReactionsDesktop = defineAsyncComponent(() => import('@/components/ReactionsDesktop.vue'))
const ReactionsUI = computed(() => (isMobile.value ? ReactionsMobile : ReactionsDesktop))
const sessionUser = useSessionUser()

const reactionsCount = computed(() => {
  const counts: Record<string, ReactionCount> = {}
  for (const [emoji, users] of Object.entries(props.reactions)) {
    counts[emoji] = { count: users.length, users, userReacted: users.includes(sessionUser.name) }
  }
  return counts
})

function toolTipText(reactions: ReactionCount) {
  return reactions.users
    .map((user) => useUser(user).full_name?.trim())
    .filter(Boolean)
    .join(', ')
}
</script>
