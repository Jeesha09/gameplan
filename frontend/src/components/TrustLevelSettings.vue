<template>
  <Button variant="ghost" icon-left="lucide-settings-2" @click="show">Trust level settings</Button>
  <Dialog v-model:open="open" title="Trust levels" :dismissible="!saving" size="6xl">
    <!-- Every requirement stays on screen without scrolling, down to a 1024 × 600 window. -->
    <div class="trust-level-settings">
      <Checkbox
        v-model="enabled"
        label="Use trust levels"
        :disabled="loading || saving"
        data-testid="trust-levels-switch"
      />
      <p class="mt-2 text-p-sm text-ink-gray-6">
        Members earn Basic, Member and Regular as they visit and take part. Leader is set by hand.
        Turning levels on works out everyone's level in the background.
      </p>
    </div>
    <div v-for="group in SETTING_GROUPS" :key="group.title" class="mt-3">
      <p class="text-base font-medium text-ink-gray-8">{{ group.title }} needs</p>
      <div class="mt-1.5 grid items-end gap-x-3 gap-y-2 sm:grid-cols-2 md:grid-cols-4 lg:grid-cols-6">
        <TextInput
          v-for="[field, label] in group.fields"
          :key="field"
          v-model="values[field]"
          :label="label"
          type="number"
          :min="ranges[field]?.[0]"
          :max="ranges[field]?.[1]"
          :disabled="loading || saving"
        />
      </div>
    </div>
    <ErrorMessage
      v-if="error"
      class="mt-3"
      :message="extractServerMessage(error) || 'Could not save the trust level settings'"
    />
    <template #actions>
      <Button
        variant="solid"
        :disabled="loading || !loaded || !valid"
        :loading="saving"
        @click="save"
        >Save trust levels</Button
      >
    </template>
  </Dialog>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button, Checkbox, Dialog, ErrorMessage, TextInput, call, toast } from 'frappe-ui'
import { extractServerMessage } from '@/utils'
import { SETTING_GROUPS, type TrustSettings } from '@/data/trustLevels'

const emit = defineEmits<{ saved: [] }>()
const open = ref(false),
  loaded = ref(false),
  loading = ref(false),
  saving = ref(false),
  enabled = ref(false),
  error = ref<unknown>(null)
const values = ref<Record<string, string>>({})
const ranges = ref<Record<string, [number, number]>>({})
const valid = computed(() =>
  Object.entries(ranges.value).every(([field, [low, high]]) => {
    const number = Number(values.value[field])
    return Number.isInteger(number) && number >= low && number <= high
  }),
)

async function show() {
  open.value = true
  error.value = null
  loading.value = true
  loaded.value = false
  try {
    const settings = await call<TrustSettings>('gameplan.trust_levels.get_settings')
    enabled.value = Boolean(settings.enabled)
    ranges.value = settings.ranges
    values.value = Object.fromEntries(
      Object.keys(settings.ranges).map((field) => [field, String(settings[field])]),
    )
    loaded.value = true
  } catch (e) {
    error.value = e
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  error.value = null
  try {
    await call('gameplan.trust_levels.save_settings', {
      enabled: enabled.value ? 1 : 0,
      ...Object.fromEntries(
        Object.entries(values.value).map(([key, value]) => [key, Number(value)]),
      ),
    })
    open.value = false
    toast.success('Trust levels saved.')
    emit('saved')
  } catch (e) {
    error.value = e
  } finally {
    saving.value = false
  }
}
</script>
<style>
/* The dialog's default 2rem margins alone would push it past a short window. */
.dialog-content:has(.trust-level-settings) {
  margin-block: 0;
}
</style>
