<template>
  <div class="mx-auto w-full max-w-3xl px-5 py-6">
    <LoadError
      v-if="loadError"
      :message="errorText(loadError, 'Could not load the badge settings.')"
      @retry="load"
    />
    <template v-else-if="loaded">
      <section>
        <Checkbox v-model="enabled" label="Use badges" :disabled="saving" />
        <p class="mt-2 text-p-sm text-ink-gray-6">
          Members earn badges as they take part. Turning badges on works out everyone's badges in
          the background, without notifying anyone. Members see the change after reloading the page.
        </p>
        <div class="mt-4 grid gap-x-6 gap-y-2 sm:grid-cols-2">
          <div v-for="badge in badges" :key="badge.name" class="flex items-center gap-2">
            <BadgeMedallion
              size="sm"
              :family="badge.family"
              :tier="badge.tier"
              :title="badge.title"
              :description="badge.description"
            />
            <Checkbox
              v-model="badgeSwitches[badge.name]"
              :label="`${badge.title} (${badge.tier})`"
              :disabled="saving || !enabled"
            />
          </div>
        </div>
        <ErrorMessage
          v-if="saveError"
          class="mt-3"
          :message="errorText(saveError, 'Could not save the badge settings.')"
        />
        <Button class="mt-4" variant="solid" :loading="saving" @click="save">Save badges</Button>
      </section>

      <section v-if="enabled" class="mt-10">
        <h2 class="text-base-medium text-ink-gray-9">Grant or take back a badge</h2>
        <p class="mt-1 text-p-sm text-ink-gray-6">
          The change and its reason go to the person's account history. A badge taken back is not
          earned again by itself. Badges earned for a post cannot be granted by hand.
        </p>
        <div class="mt-3 grid gap-3 sm:grid-cols-2">
          <UserCombobox v-model="person" placeholder="Choose a person" />
          <Select v-model="chosenBadge" :options="manualOptions" placeholder="Choose a badge" />
        </div>
        <Textarea
          v-model="reason"
          class="mt-3"
          label="Reason"
          :rows="2"
          placeholder="Shown in the person's account history"
        />
        <ErrorMessage
          v-if="manualError"
          class="mt-3"
          :message="errorText(manualError, 'Could not change the badge.')"
        />
        <div class="mt-3 flex gap-2">
          <Button
            :disabled="!canChange"
            :loading="changing === 'grant'"
            @click="change('grant_badge')"
            >Grant</Button
          >
          <Button
            :disabled="!person || !chosenBadge || !reason.trim()"
            :loading="changing === 'revoke'"
            @click="change('revoke_badge')"
            >Take back</Button
          >
        </div>
      </section>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button, Checkbox, ErrorMessage, Select, Textarea, call, toast } from 'frappe-ui'
import BadgeMedallion from '@/components/Badges/BadgeMedallion.vue'
import LoadError from '@/components/LoadError.vue'
import UserCombobox from '@/components/UserCombobox.vue'
import type { BadgeTier } from '@/data/badges'
import { errorText } from '@/utils'

type SettingsBadge = {
  name: string
  title: string
  description: string
  family: string
  tier: BadgeTier
  enabled: 0 | 1
  per_post: 0 | 1
}
type Settings = { enabled: 0 | 1; badges: SettingsBadge[] }

const loaded = ref(false),
  enabled = ref(false),
  saving = ref(false),
  loadError = ref<unknown>(null),
  saveError = ref<unknown>(null)
const badges = ref<SettingsBadge[]>([])
const badgeSwitches = ref<Record<string, boolean>>({})

const person = ref<string | null>(null),
  chosenBadge = ref(''),
  reason = ref(''),
  changing = ref<'' | 'grant' | 'revoke'>(''),
  manualError = ref<unknown>(null)
const manualOptions = computed(() =>
  badges.value
    .filter((badge) => badge.enabled)
    .map((badge) => ({ label: badge.title, value: badge.name })),
)
const canChange = computed(
  () =>
    Boolean(person.value && chosenBadge.value && reason.value.trim()) &&
    !badges.value.find((badge) => badge.name === chosenBadge.value)?.per_post,
)

function apply(settings: Settings) {
  enabled.value = Boolean(settings.enabled)
  badges.value = settings.badges
  badgeSwitches.value = Object.fromEntries(settings.badges.map((b) => [b.name, Boolean(b.enabled)]))
  loaded.value = true
}

async function load() {
  loadError.value = null
  try {
    apply(await call<Settings>('gameplan.badges.api.get_settings'))
  } catch (error) {
    loadError.value = error
  }
}

async function save() {
  saving.value = true
  saveError.value = null
  try {
    const disabled = Object.entries(badgeSwitches.value)
      .filter(([, on]) => !on)
      .map(([name]) => name)
    apply(
      await call<Settings>('gameplan.badges.api.save_settings', {
        enabled: enabled.value ? 1 : 0,
        disabled_badges: disabled,
      }),
    )
    toast.success('Badges saved.')
  } catch (error) {
    saveError.value = error
  } finally {
    saving.value = false
  }
}

async function change(method: 'grant_badge' | 'revoke_badge') {
  changing.value = method === 'grant_badge' ? 'grant' : 'revoke'
  manualError.value = null
  try {
    await call(`gameplan.badges.api.${method}`, {
      user: person.value,
      badge: chosenBadge.value,
      reason: reason.value.trim(),
    })
    toast.success(method === 'grant_badge' ? 'Badge granted.' : 'Badge taken back.')
    reason.value = ''
  } catch (error) {
    manualError.value = error
  } finally {
    changing.value = ''
  }
}

load()
</script>
