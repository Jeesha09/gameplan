<template>
  <BadgeTooltip
    :title="badge.title"
    :tier="badge.tier"
    :description="badge.description"
    :granted-at="badge.granted_at"
    :count="badge.count"
  >
    <router-link
      :to="{ name: 'Badge', params: { badgeId: badge.name } }"
      class="badge-ribbon block rounded-sm focus-visible:focus-ring"
      :class="[`badge-tier--${badge.tier.toLowerCase()}`, { 'badge-ribbon--playing': playing }]"
      :aria-label="`${badge.title}, ${badge.tier} badge`"
      :aria-description="badge.description || undefined"
      @mouseenter="play"
      @focus="play"
      @animationend.self="stop"
    >
      <svg class="h-[31px] w-[26px]" viewBox="0 0 64 76" aria-hidden="true">
        <path
          fill="var(--badge-ring)"
          d="M6 2h52a2 2 0 0 1 2 2v53.5c0 .8-.5 1.5-1.2 1.8L32 72 5.2 59.3A2 2 0 0 1 4 57.5V4a2 2 0 0 1 2-2z"
        />
        <path fill="var(--badge-panel)" d="M7.5 5.5h49v51.2L32 68.3 7.5 56.7z" />
        <!-- eslint-disable-next-line vue/no-v-html -- constant symbol markup from data/badges.ts -->
        <g
          class="badge-art"
          transform="translate(12.8 13) scale(1.6)"
          v-html="BADGE_SYMBOLS[badge.family] || ''"
        />
      </svg>
    </router-link>
  </BadgeTooltip>
</template>
<script setup lang="ts">
import BadgeTooltip from './BadgeTooltip.vue'
import { useReplay } from './useReplay'
import { BADGE_SYMBOLS, type HeldBadge } from '@/data/badges'

defineProps<{ badge: HeldBadge }>()

// A ribbon hangs from the card's top edge, so hovering swings it from there.
const { playing, play, stop } = useReplay()
</script>
<style>
.badge-ribbon {
  --badge-cut: var(--badge-panel);
  transform-origin: 50% 0;
}
.badge-ribbon--playing {
  animation: badge-ribbon-swing 900ms ease-out;
}
@keyframes badge-ribbon-swing {
  20% {
    transform: rotate(9deg);
  }
  45% {
    transform: rotate(-6deg);
  }
  70% {
    transform: rotate(3deg);
  }
  88% {
    transform: rotate(-1deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .badge-ribbon--playing {
    animation: none;
  }
}
</style>
