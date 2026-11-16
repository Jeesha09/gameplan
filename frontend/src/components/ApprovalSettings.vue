<template>
  <Button variant="ghost" icon-left="lucide-settings-2" @click="show">Approval settings</Button>
  <Dialog v-model:open="open" title="Community post approval" :dismissible="!saving">
    <p class="mb-4 text-base text-ink-gray-6">
      Review new contributors' discussions and replies before publication. Community staff are
      exempt.<template v-if="!levelsEnabled">
        Existing published contributions count toward the threshold.</template
      >
    </p>
    <template v-if="levelsEnabled">
      <Select
        v-model="minLevel"
        label="Hold posts for approval from"
        :options="levelPolicies"
        :disabled="loading || saving"
        data-testid="approval-level"
      />
      <p class="mt-2 text-p-sm text-ink-gray-6">
        Trust levels are on for the site, so levels decide who needs approval here. A global admin
        sets the level requirements under Site administration.
      </p>
    </template>
    <Checkbox
      v-else
      v-model="enabled"
      label="Require approval for new contributors"
      :disabled="loading || saving"
    />
    <TextInput
      v-if="enabled && !levelsEnabled"
      v-model="count"
      class="mt-4"
      label="Accepted contributions needed to post freely"
      type="number"
      :min="1"
      :max="100"
      :disabled="loading || saving"
    />
    <p class="mt-3 text-base text-ink-gray-5">
      Changes affect future submissions. Existing pending submissions still need a decision.
    </p>
    <section class="mt-6 border-t border-outline-gray-1 pt-5" aria-labelledby="auto-hide-title">
      <h3 id="auto-hide-title" class="text-base font-medium text-ink-gray-8">Auto-hide</h3>
      <p class="mt-1 text-p-sm text-ink-gray-6">
        Hide a post until review when its Spam and Abuse reports reach a weight. New and Basic
        members count 1, Members 2, Regulars, Leaders and Community staff 3. Posts by Community
        staff never hide.
      </p>
      <Checkbox
        v-model="autoHideEnabled"
        class="mt-3"
        label="Hide reported posts automatically"
        :disabled="loading || saving || (!levelsEnabled && !autoHideEnabled)"
        data-testid="auto-hide-switch"
      />
      <p v-if="!levelsEnabled" class="mt-2 text-p-sm text-ink-gray-6">
        Auto-hide needs trust levels. A global admin turns them on under Site administration.
        <template v-if="autoHideEnabled">Until then, auto-hide is paused.</template>
      </p>
      <TextInput
        v-if="autoHideEnabled"
        v-model="threshold"
        class="mt-4"
        label="Report weight that hides a post"
        type="number"
        :min="3"
        :max="30"
        :disabled="loading || saving"
        data-testid="auto-hide-threshold"
      />
    </section>
    <ErrorMessage
      v-if="error"
      class="mt-3"
      :message="extractServerMessage(error) || 'Could not update approval settings'"
    />
    <template #actions
      ><Button
        variant="solid"
        :disabled="
          loading ||
          !loaded ||
          (enabled &&
            !levelsEnabled &&
            (!Number.isInteger(Number(count)) || Number(count) < 1 || Number(count) > 100)) ||
          !thresholdValid
        "
        :loading="saving"
        @click="save"
        >Save approval policy</Button
      ></template
    >
  </Dialog>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button, Checkbox, Dialog, ErrorMessage, Select, TextInput, call, toast } from 'frappe-ui'
import { extractServerMessage } from '@/utils'
const props = defineProps<{ communityId: string }>()
const levelPolicies = [
  { label: 'Nobody', value: '' },
  { label: 'New members', value: 'Basic' },
  { label: 'New and Basic members', value: 'Member' },
]
const loaded = ref(false)
const open = ref(false),
  enabled = ref(false),
  count = ref('3'),
  levelsEnabled = ref(false),
  minLevel = ref(''),
  loading = ref(false),
  saving = ref(false),
  error = ref<unknown>(null)
const autoHideEnabled = ref(false),
  threshold = ref('6')
const thresholdValid = computed(() => {
  const number = Number(threshold.value)
  return Number.isInteger(number) && number >= 3 && number <= 30
})
type AutoHideSettings = { enabled: number; threshold: number }
async function show() {
  open.value = true
  error.value = null
  loading.value = true
  loaded.value = false
  try {
    const [value, levels, autoHide] = await Promise.all([
      call<number>('gameplan.approval_policy.get_policy', { community: props.communityId }),
      call<{ levels_enabled: boolean; min_level: string }>(
        'gameplan.approval_policy.get_level_policy',
        { community: props.communityId },
      ),
      call<AutoHideSettings>('gameplan.auto_hide.get_settings', { community: props.communityId }),
    ])
    autoHideEnabled.value = Boolean(autoHide.enabled)
    threshold.value = String(autoHide.threshold)
    levelsEnabled.value = Boolean(levels.levels_enabled)
    minLevel.value = levels.min_level
    loaded.value = true
    enabled.value = value > 0
    count.value = String(value || 3)
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
    if (levelsEnabled.value)
      await call('gameplan.approval_policy.set_level_policy', {
        community: props.communityId,
        min_level: minLevel.value,
      })
    else
      await call('gameplan.approval_policy.set_policy', {
        community: props.communityId,
        count: enabled.value ? Number(count.value) : 0,
      })
    await call('gameplan.auto_hide.save_settings', {
      community: props.communityId,
      enabled: autoHideEnabled.value ? 1 : 0,
      threshold: Number(threshold.value),
    })
    open.value = false
    toast.success('Approval policy saved.')
  } catch (e) {
    error.value = e
  } finally {
    saving.value = false
  }
}
</script>
