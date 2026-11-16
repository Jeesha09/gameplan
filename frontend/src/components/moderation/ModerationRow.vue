<template>
  <div
    class="flex items-center gap-3 border-b border-outline-gray-1 py-3 last:border-b-0"
    data-testid="moderation-row"
  >
    <div v-if="$slots.select" class="flex w-5 shrink-0 justify-center"><slot name="select" /></div>
    <div v-if="$slots.lead" class="flex w-7 shrink-0 justify-center self-start pt-0.5">
      <slot name="lead" />
    </div>
    <div class="min-w-0 flex-1">
      <p class="truncate text-base font-medium text-ink-gray-9"><slot name="title" /></p>
      <div v-if="$slots.status" class="mt-1 flex flex-wrap gap-1 sm:hidden">
        <slot name="status" />
      </div>
      <p v-if="$slots.detail" class="mt-1 line-clamp-2 break-words text-p-sm text-ink-gray-7">
        <slot name="detail" />
      </p>
      <p v-if="$slots.meta" class="mt-1 truncate text-p-sm text-ink-gray-5"><slot name="meta" /></p>
    </div>
    <div v-if="$slots.status" class="hidden w-44 shrink-0 flex-wrap justify-end gap-1 sm:flex">
      <slot name="status" />
    </div>
    <div class="flex shrink-0 items-center justify-end gap-1 sm:w-32"><slot name="actions" /></div>
  </div>
</template>
