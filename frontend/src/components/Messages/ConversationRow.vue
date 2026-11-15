<template>
  <div class="group relative">
    <router-link
      :to="{ name: 'Conversation', params: { conversationId: row.name } }"
      class="flex items-center gap-3 rounded-5 px-2.5 py-2 transition"
      :class="active ? 'bg-surface-gray-3' : 'hover:bg-surface-gray-2'"
    >
      <UserAvatar v-if="row.people[0]" :user="row.people[0]" size="xl" class="shrink-0" />
      <div class="min-w-0 flex-1">
        <div class="flex items-baseline justify-between gap-2">
          <span class="flex min-w-0 items-center gap-1">
            <span
              class="truncate"
              :class="unread ? 'text-base-medium text-ink-gray-9' : 'text-base text-ink-gray-8'"
            >
              {{ title }}
            </span>
            <span
              v-if="row.muted"
              class="lucide-bell-off size-3.5 shrink-0 text-ink-gray-4"
              aria-label="Muted"
            />
          </span>
          <span
            v-if="row.last_message_at"
            class="shrink-0 text-sm text-ink-gray-5"
            :class="
              !isMobile &&
              'transition-opacity group-hover:opacity-0 group-has-[:focus-visible]:opacity-0 group-has-[[data-state=open]]:opacity-0'
            "
          >
            {{ relativeTimestamp(row.last_message_at) }}
          </span>
        </div>
        <div class="mt-0.5 flex items-center justify-between gap-2">
          <span class="truncate text-sm" :class="unread ? 'text-ink-gray-7' : 'text-ink-gray-5'">
            <template v-if="row.last_message_preview && row.last_message_by === sessionUser.name">
              You:
            </template>
            <template v-if="row.last_message_preview">{{ row.last_message_preview }}</template>
          </span>
          <span
            v-if="row.unread_count"
            class="flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full px-1.5 text-xs-medium tabular-nums"
            :class="[
              row.muted ? 'bg-surface-gray-2 text-ink-gray-5' : 'bg-surface-gray-4 text-ink-gray-7',
              !isMobile &&
                'transition-opacity group-hover:opacity-0 group-has-[:focus-visible]:opacity-0 group-has-[[data-state=open]]:opacity-0',
            ]"
          >
            {{ formatUnreadCount(row.unread_count) }}
          </span>
        </div>
      </div>
    </router-link>
    <div
      v-if="!isMobile"
      class="absolute right-1.5 top-1.5 opacity-0 transition-opacity group-hover:opacity-100 group-has-[:focus-visible]:opacity-100 has-[[data-state=open]]:opacity-100"
    >
      <DropdownMoreOptions
        :options="conversationActions(row, router)"
        align="end"
        label="Conversation options"
        button-size="xs"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import DropdownMoreOptions from '@/components/DropdownMoreOptions.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import type { Conversation } from '@/data/messages'
import { useSessionUser, useUser } from '@/data/users'
import { relativeTimestamp } from '@/utils'
import { formatUnreadCount } from '@/utils/formatters'
import { useIsMobile } from '@/utils/useIsMobile'
import { conversationActions } from './conversationActions'

const props = defineProps<{
  row: Conversation
  active?: boolean
}>()

const router = useRouter()
const isMobile = useIsMobile()
const sessionUser = useSessionUser()
const unread = computed(() => Boolean(props.row.unread_count) && !props.row.muted)
const title = computed(() => props.row.people.map((user) => useUser(user).full_name).join(', '))
</script>
