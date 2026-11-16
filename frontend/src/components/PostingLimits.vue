<template>
  <div class="text-ink-gray-9">
    <p class="pb-5 text-p-base text-ink-gray-6">
      Site-wide limits for every Community. Global admins are exempt. Windows use elapsed time, so
      they work the same in every time zone.
    </p>
    <div v-if="policy">
      <section class="border-t border-outline-gray-1 py-5">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h2 class="text-base font-medium">Posting rate</h2>
            <p class="mt-1 text-p-sm text-ink-gray-6">
              How many new discussions and replies one account can post. Activity is counted even
              while this is off. Pending submissions count once.
            </p>
          </div>
          <Switch v-model="policy.enabled" aria-label="Enable posting limits" />
        </div>
        <div
          v-if="policy.enabled"
          class="mt-4 grid max-w-md grid-cols-[1fr_6rem_6rem] items-center gap-x-3 gap-y-2"
        >
          <span />
          <span class="text-p-sm text-ink-gray-6">Per hour</span>
          <span class="text-p-sm text-ink-gray-6">Per 24 hours</span>
          <template v-for="row in rateRows" :key="row.label">
            <span class="text-base">{{ row.label }}</span>
            <FormControl
              v-for="key in row.keys"
              :key="key"
              v-model="policy[key]"
              type="number"
              :min="0"
              :max="10000"
              :aria-label="labels[key]"
            />
          </template>
        </div>
      </section>
      <section class="border-t border-outline-gray-1 py-5">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h2 class="text-base font-medium">Content caps</h2>
            <p class="mt-1 text-p-sm text-ink-gray-6">
              The most links, images, files and mentions one post can include. Community staff are
              exempt in their own Communities.
            </p>
          </div>
          <Switch v-model="policy.caps_enabled" aria-label="Enable content caps" />
        </div>
        <div
          v-if="policy.caps_enabled"
          class="mt-4 grid max-w-md grid-cols-[1fr_6rem_6rem] items-center gap-x-3 gap-y-2"
        >
          <template v-for="field in caps" :key="field.key">
            <span class="text-base">{{ field.label }}</span>
            <FormControl
              v-model="policy[field.key]"
              type="number"
              :min="0"
              :max="10000"
              :aria-label="field.label"
            />
            <span />
          </template>
        </div>
      </section>
      <div class="flex items-center gap-3 border-t border-outline-gray-1 pt-5">
        <Button variant="solid" :loading="saving" @click="save">Save</Button>
        <p v-if="saved" role="status" class="text-p-sm text-ink-gray-6">Posting limits saved</p>
        <p v-else class="text-p-sm text-ink-gray-5">0 turns off a single limit.</p>
        <ErrorMessage :message="error" />
      </div>
    </div>
    <ErrorMessage v-else :message="error" class="pt-6" />
  </div>
</template>
<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { Button, ErrorMessage, FormControl, Switch, call } from 'frappe-ui'
import { extractServerMessage } from '@/utils'

const fields = [
  { key: 'discussions_hour', label: 'Discussions per hour' },
  { key: 'discussions_day', label: 'Discussions per 24 hours' },
  { key: 'replies_hour', label: 'Replies per hour' },
  { key: 'replies_day', label: 'Replies per 24 hours' },
] as const
const rateRows = [
  { label: 'Discussions', keys: ['discussions_hour', 'discussions_day'] },
  { label: 'Replies', keys: ['replies_hour', 'replies_day'] },
] as const
const labels: Record<string, string> = Object.fromEntries(fields.map((f) => [f.key, f.label]))
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
