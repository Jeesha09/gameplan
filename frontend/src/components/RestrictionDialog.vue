<template>
  <Dialog v-model:open="open" :title="title" :dismissible="!saving">
    <p class="mb-4 text-base text-ink-gray-6">
      {{ user.full_name || user.user }} ·
      {{
        community
          ? 'Participation in this Community'
          : kind === 'Silence'
            ? 'Participation in every Community'
            : 'Entire Frappe site, including all installed apps and API access'
      }}
    </p>
    <template v-if="!community && !lifting">
      <Select
        v-model="kind"
        label="Restriction"
        :options="[
          { label: 'Silence', value: 'Silence' },
          { label: 'Suspend', value: 'Suspend' },
        ]"
        :disabled="saving"
      />
      <p class="mb-3 mt-2 text-p-sm text-ink-gray-6">
        Silence: can sign in and read, but can't post anywhere. Suspend: can't sign in or use the
        site at all.
      </p>
    </template>
    <Select
      v-if="!lifting"
      v-model="duration"
      label="Duration"
      :options="durations"
      :disabled="saving"
    />
    <DateTimePicker
      v-if="!lifting && duration === 'custom'"
      v-model="custom"
      class="mt-3"
      label="Expires at"
      :disabled="saving"
    />
    <p v-if="!lifting" class="mt-2 text-p-sm text-ink-gray-6">
      Times shown in {{ timezone }}. One day means 24 hours.
      <span v-if="user.expires_at">Current expiry: {{ expiryLabel(user.expires_at) }}.</span>
    </p>
    <p v-if="!lifting && duration === 'custom' && custom" class="mt-2 text-p-sm text-ink-gray-6">
      Selected expiry: {{ dayjsLocal(custom).format('D MMM YYYY, h:mm A [UTC]Z') }}
    </p>
    <Textarea
      v-model="reason"
      class="mt-4"
      label="Reason (shared with this person)"
      :maxlength="500"
      :disabled="saving"
      required
    />
    <Checkbox
      v-if="!lifting"
      v-model="cleanup"
      class="mt-3"
      label="Also remove all their posts"
      :disabled="saving"
    />
    <ErrorMessage
      v-if="error"
      class="mt-3"
      :message="extractServerMessage(error) || 'Could not update the restriction'"
    />
    <template #actions>
      <Button
        variant="solid"
        :loading="saving"
        :disabled="!reason.trim() || (!lifting && duration === 'custom' && !custom)"
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
