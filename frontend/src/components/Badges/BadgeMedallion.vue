<template>
  <Tooltip :hover-delay="200">
    <button
      type="button"
      class="badge-medallion relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full focus-visible:focus-ring"
      :class="[
        `badge-medallion--${tier.toLowerCase()}`,
        sizes[size].frame,
        { 'badge-medallion--playing': playing },
      ]"
      :aria-label="`${title}, ${tier} badge`"
      :aria-description="description || undefined"
      @mouseenter="play"
      @click.stop.prevent="play"
      @animationend.self="playing = false"
    >
      <!-- eslint-disable-next-line vue/no-v-html -- constant symbol markup from data/badges.ts -->
      <svg
        :class="sizes[size].symbol"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
        v-html="BADGE_SYMBOLS[family] || ''"
      />
    </button>
    <template #content>
      <div class="max-w-56 py-0.5">
        <div class="font-medium">{{ title }} · {{ tier }}</div>
        <div v-if="description" class="mt-0.5 opacity-80">{{ description }}</div>
      </div>
    </template>
  </Tooltip>
</template>
<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { Tooltip } from 'frappe-ui'
import { BADGE_SYMBOLS, type BadgeTier } from '@/data/badges'

withDefaults(
  defineProps<{
    family: string
    tier: BadgeTier
    title: string
    /** What the badge is for, shown in the tooltip. */
    description?: string
    size?: 'sm' | 'md' | 'lg'
  }>(),
  { size: 'md', description: '' },
)

const sizes = {
  sm: { frame: 'size-6 border-[1.5px]', symbol: 'size-3.5' },
  md: { frame: 'size-10 border-2', symbol: 'size-5' },
  lg: { frame: 'size-16 border-[3px]', symbol: 'size-8' },
}

// Hovering or clicking flips the medallion like a coin. A click never follows a link the
// medallion sits in, so the flip can be seen; the badge's name next to it is the link.
const playing = ref(false)
async function play() {
  playing.value = false
  await nextTick()
  playing.value = true
}
</script>
<style>
/* Tier colours are Discourse's, approved in prd/badges.md as the one exception to the
   gray-token rule for badge medallions. */
.badge-medallion--bronze {
  background: var(--badge-bronze-fill);
  border-color: var(--badge-bronze-ring);
  color: var(--badge-bronze-symbol);
}
.badge-medallion--silver {
  background: var(--badge-silver-fill);
  border-color: var(--badge-silver-ring);
  color: var(--badge-silver-symbol);
}
.badge-medallion--gold {
  background: var(--badge-gold-fill);
  border-color: var(--badge-gold-ring);
  color: var(--badge-gold-symbol);
}

.badge-medallion--playing {
  animation: badge-medallion-flip 700ms cubic-bezier(0.34, 1.3, 0.64, 1);
}
/* A light band crosses the face while it turns. */
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
@keyframes badge-medallion-flip {
  0% {
    transform: perspective(200px) rotateY(0) scale(1);
  }
  45% {
    transform: perspective(200px) rotateY(200deg) scale(1.15);
  }
  100% {
    transform: perspective(200px) rotateY(360deg) scale(1);
  }
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
  .badge-medallion--playing {
    animation: badge-medallion-pulse 300ms ease-out;
  }
  .badge-medallion--playing::after {
    display: none;
  }
  @keyframes badge-medallion-pulse {
    50% {
      transform: scale(1.08);
    }
  }
}
</style>
