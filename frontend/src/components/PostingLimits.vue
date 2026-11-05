<template>
  <div class="max-w-3xl space-y-6">
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
      <div class="divide-y divide-outline-gray-1">
        <SettingsRow
          title="Enable content caps"
          description="Limit links, images, files and mentions in each post. Community staff are exempt in their Communities."
        >
          <Switch v-model="policy.caps_enabled" />
        </SettingsRow>
        <SettingsRow
          v-for="field in policy.caps_enabled ? caps : []"
          :key="field.key"
          :title="field.label"
          description="0 removes this cap"
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
const caps = [
  { key: 'max_links', label: 'Links per post' },
  { key: 'max_images', label: 'Images per post' },
  { key: 'max_attachments', label: 'Files and videos per post' },
  { key: 'max_mentions', label: 'Mentions per post' },
] as const
type Policy = { enabled: boolean; caps_enabled: boolean } & Record<
  (typeof fields)[number]['key'] | (typeof caps)[number]['key'],
  number
>
const policy = ref<Policy | null>(null)
const error = ref('')
const saving = ref(false)
const saved = ref(false)
watch(policy, () => (saved.value = false), { deep: true })
onMounted(async () => {
  try {
    const data = await call('gameplan.posting_limits.settings')
    policy.value = {
      ...data,
      enabled: Boolean(data.enabled),
      caps_enabled: Boolean(data.caps_enabled),
    }
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
      caps_enabled: Number(policy.value.caps_enabled),
    })
    saved.value = true
  } catch (e) {
    error.value = extractServerMessage(e) || 'Could not save posting limits'
  } finally {
    saving.value = false
  }
}
</script>
