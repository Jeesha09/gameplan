<template>
  <Dialog v-model:open="open" :title="title" :dismissible="!saving">
    <div class="flex flex-col gap-5">
      <slot name="person" />
      <p v-if="user.user && !$slots.person" class="text-base text-ink-gray-6">
        {{ user.full_name || user.user }}
      </p>
      <Select
        v-if="!community && !lifting"
        v-model="kind"
        label="Restriction"
        :description="kind === 'Silence' ? 'Can read, but can\'t post' : 'Can\'t sign in at all'"
        :options="[
          { label: 'Silence', value: 'Silence' },
          { label: 'Suspend', value: 'Suspend' },
        ]"
        :disabled="saving"
      />
      <div v-if="!lifting" class="flex flex-col gap-3">
        <Select v-model="duration" label="Duration" :options="durations" :disabled="saving" />
        <p v-if="user.expires_at && duration === 'keep'" class="text-p-sm text-ink-gray-6">
          Ends {{ expiryLabel(user.expires_at) }}
        </p>
        <template v-if="duration === 'custom'">
          <DateTimePicker v-model="custom" label="Ends at" :disabled="saving" />
          <p class="text-p-sm text-ink-gray-6">Times are in {{ timezone }}</p>
        </template>
      </div>
      <Textarea
        v-model="reason"
        label="Reason (shared with this person)"
        :maxlength="500"
        :disabled="saving"
        required
      />
      <Checkbox
        v-if="!lifting"
        v-model="cleanup"
        label="Also remove all their posts"
        :disabled="saving"
      />
      <ErrorMessage
        v-if="error"
        :message="extractServerMessage(error) || 'Could not update the restriction'"
      />
    </div>
    <template #actions>
      <Button
        variant="solid"
        :loading="saving"
        :disabled="!user.user || !reason.trim() || (!lifting && duration === 'custom' && !custom)"
        @click="save"
        >{{ lifting ? 'Lift restriction' : 'Save restriction' }}</Button
      >
    </template>
  </Dialog>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  Button,
  Checkbox,
  DateTimePicker,
  Dialog,
  ErrorMessage,
  Select,
  Textarea,
  call,
  dayjsLocal,
  getConfig,
  toast,
} from 'frappe-ui'
import { extractServerMessage } from '@/utils'
import {
  durationPresets,
  expiryLabel,
  startCleanup,
  type RestrictionUser,
} from '@/data/restrictions'
const props = defineProps<{ user: RestrictionUser; community?: string; lifting?: boolean }>()
const open = defineModel<boolean>('open')
const emit = defineEmits<{ saved: [] }>()
const duration = ref(props.user.modified ? 'keep' : '0')
const custom = ref('')
const reason = ref('')
const kind = ref(props.user.kind || 'Silence')
const cleanup = ref(false)
const saving = ref(false)
const error = ref<unknown>(null)
const timezone = getConfig('localTimezone') || Intl.DateTimeFormat().resolvedOptions().timeZone
const title = computed(() =>
  props.lifting
    ? 'Lift restriction'
    : props.community
      ? 'Community ban'
      : 'Restrict account across this site',
)
const durations = [
  ...(props.user.modified ? [{ label: 'Keep current expiry', value: 'keep' }] : []),
  { label: 'Until manually lifted', value: '0' },
  ...durationPresets,
]
async function save() {
  saving.value = true
  error.value = null
  try {
    await call('gameplan.restrictions.set_restriction', {
      user: props.user.user,
      community: props.community || '',
      enabled: props.lifting ? 0 : 1,
      reason: reason.value,
      expected_modified: props.user.modified || '',
      ...(props.community || props.lifting ? {} : { kind: kind.value }),
      ...(duration.value === 'custom'
        ? { expires_at: dayjsLocal(custom.value).toISOString() }
        : duration.value === 'keep'
          ? { expires_at: props.user.expires_at || '' }
          : { duration_seconds: Number(duration.value) }),
    })
    toast.success('Restriction updated')
    if (cleanup.value) await startCleanup(props.user.user, reason.value, props.community)
    emit('saved')
    open.value = false
  } catch (e) {
    error.value = e
  } finally {
    saving.value = false
  }
}
</script>
