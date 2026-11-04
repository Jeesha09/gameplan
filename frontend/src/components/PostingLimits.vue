<template>
  <div class="max-w-3xl space-y-6">
    <h2 class="border-b border-outline-gray-2 pb-4 text-lg-semibold text-ink-gray-9">
      Posting limits
    </h2>
    <div v-if="policy" class="space-y-6">
      <p class="text-base text-ink-gray-6">
        Per-account limits across all Communities. Global admins are exempt. Pending submissions
        count once. Windows use elapsed time in every time zone.
      </p>
      <div class="divide-y divide-outline-gray-1">
        <SettingsRow
          title="Enable posting limits"
          description="Track activity even while limits are off"
        >
          <Switch v-model="policy.enabled" />
        </SettingsRow>
        <SettingsRow
          v-for="field in policy.enabled ? fields : []"
          :key="field.key"
          :title="field.label"
          description="0 disables this limit"
        >
          <FormControl
            v-model="policy[field.key]"
            type="number"
            :min="0"
            :max="10000"
            class="w-24"
            :aria-label="field.label"
          />
        </SettingsRow>
      </div>
      <ErrorMessage :message="error" />
      <div class="flex items-center gap-3">
        <Button variant="solid" :loading="saving" @click="save">Save</Button>
        <p v-if="saved" role="status" class="text-base text-ink-gray-6">Posting limits saved</p>
      </div>
    </div>
    <ErrorMessage v-else :message="error" class="pt-6" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { Button, ErrorMessage, FormControl, SettingsRow, Switch, call } from 'frappe-ui'
import { extractServerMessage } from '@/utils'

const fields = [
  { key: 'discussions_hour', label: 'Discussions per hour' },
  { key: 'discussions_day', label: 'Discussions per 24 hours' },
  { key: 'replies_hour', label: 'Replies per hour' },
  { key: 'replies_day', label: 'Replies per 24 hours' },
] as const
type Policy = { enabled: boolean } & Record<(typeof fields)[number]['key'], number>
const policy = ref<Policy | null>(null)
const error = ref('')
const saving = ref(false)
const saved = ref(false)
watch(policy, () => (saved.value = false), { deep: true })
onMounted(async () => {
  try {
    const data = await call('gameplan.posting_limits.settings')
    policy.value = { ...data, enabled: Boolean(data.enabled) }
  } catch (e) {
    error.value = extractServerMessage(e) || 'Could not load posting limits'
  }
})
async function save() {
  if (!policy.value) return
  saving.value = true
  error.value = ''
  try {
    await call('gameplan.posting_limits.save_settings', {
      ...policy.value,
      enabled: Number(policy.value.enabled),
    })
    saved.value = true
  } catch (e) {
    error.value = extractServerMessage(e) || 'Could not save posting limits'
  } finally {
    saving.value = false
  }
}
</script>
