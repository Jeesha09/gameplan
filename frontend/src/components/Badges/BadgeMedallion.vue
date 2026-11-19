<template>
  <BadgeTooltip
    :title="title"
    :tier="tier"
    :description="description"
    :granted-at="grantedAt"
    :count="count"
    :disabled="!tooltip"
  >
    <button
      type="button"
      class="badge-medallion relative inline-flex shrink-0 overflow-hidden rounded-full focus-visible:focus-ring"
      :class="[
        `badge-tier--${tier.toLowerCase()}`,
        sizes[size],
        { 'badge-medallion--playing': playing },
      ]"
      :aria-label="`${title}, ${tier} badge`"
      :aria-description="description || undefined"
      @mouseenter="play"
      @click.stop.prevent="play"
      @animationend.self="stop"
    >
      <svg class="size-full" viewBox="0 0 40 40" aria-hidden="true">
        <circle cx="20" cy="20" r="19" fill="var(--badge-ring)" />
        <circle cx="20" cy="20" r="17.2" fill="var(--badge-face)" />
        <!-- The engraved rim is lost at the smallest size, so it is left out there. -->
        <circle
          v-if="size !== 'sm'"
          cx="20"
          cy="20"
          r="15.4"
          fill="none"
          stroke="var(--badge-symbol)"
          stroke-opacity="0.28"
          stroke-width="0.8"
          stroke-dasharray="1.6 1.4"
        />
        <!-- eslint-disable-next-line vue/no-v-html -- constant symbol markup from data/badges.ts -->
        <g
          class="badge-art"
          transform="translate(8.6 8.6) scale(0.95)"
          v-html="BADGE_SYMBOLS[family] || ''"
        />
      </svg>
    </button>
  </BadgeTooltip>
</template>
<script setup lang="ts">
import BadgeTooltip from './BadgeTooltip.vue'
import { useReplay } from './useReplay'
import { BADGE_SYMBOLS, type BadgeTier } from '@/data/badges'

withDefaults(
  defineProps<{
    family: string
    tier: BadgeTier
    title: string
    /** What the badge is for, shown in the tooltip. */
    description?: string
    grantedAt?: string
    count?: number
    size?: 'sm' | 'md' | 'lg'
    /** Shows the tooltip on hover. The shine plays either way. */
    tooltip?: boolean
  }>(),
  { size: 'md', description: '', grantedAt: '', count: 1, tooltip: true },
)

const sizes = { sm: 'size-6', md: 'size-10', lg: 'size-16' }

// Hovering or clicking runs a shine across the coin. A click never follows a link the
// medallion sits in, so the shine can be seen; the badge's name next to it is the link.
const { playing, play, stop } = useReplay()
</script>
<style>
.badge-medallion {
  --badge-cut: var(--badge-face);
}
/* A light band crosses the face. */
.badge-medallion--playing::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    115deg,
    transparent 30%,
    rgb(255 255 255 / 0.65) 50%,
    transparent 70%
  );
  animation: badge-medallion-shine 700ms ease-out;
  pointer-events: none;
}
@keyframes badge-medallion-shine {
  from {
    transform: translateX(-100%);
  }
  to {
    transform: translateX(100%);
  }
}
@media (prefers-reduced-motion: reduce) {
  .badge-medallion--playing::after {
    display: none;
  }
}
</style>
