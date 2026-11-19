<template>
  <div class="text-ink-gray-9">
    <LoadError
      v-if="loadError"
      :message="errorText(loadError, 'Could not load the badge settings.')"
      @retry="load"
    />
    <template v-else-if="loaded">
      <section>
        <div class="flex items-center justify-between gap-3">
          <Checkbox v-model="enabled" label="Use badges" :disabled="saving" />
          <Button variant="solid" :loading="saving" @click="save">Save badges</Button>
        </div>
        <ErrorMessage
          v-if="saveError"
          class="mt-3"
          :message="errorText(saveError, 'Could not save the badge settings.')"
        />
        <p class="mt-2 text-p-sm text-ink-gray-6">
          Members earn badges as they take part. Turning badges on works out everyone's badges in
          the background, without notifying anyone. Members see the change after reloading the page.
        </p>
        <!-- Like the section below, the list is only there while badges are on. -->
        <div v-if="enabled" class="mt-5">
          <div class="flex flex-wrap items-center gap-3">
            <TextInput
              v-model="search"
              class="min-w-48 flex-1"
              type="search"
              placeholder="Search badges"
              aria-label="Search badges"
            >
              <template #prefix>
                <span class="lucide-search size-4 text-ink-gray-5" aria-hidden="true" />
              </template>
            </TextInput>
            <span class="text-p-sm text-ink-gray-6" data-badge-count>
              {{ onCount }} of {{ badges.length }} on
            </span>
          </div>
          <p v-if="!groups.length" class="mt-4 text-p-sm text-ink-gray-6">
            No badge matches "{{ search.trim() }}".
          </p>
          <div v-for="group in groups" :key="group.title" class="mt-4">
            <h3 class="pb-1 text-xs font-medium uppercase tracking-wide text-ink-gray-5">
              {{ group.title }}
            </h3>
            <ul class="divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2">
              <li
                v-for="badge in group.badges"
                :key="badge.name"
                class="flex items-center gap-3 px-3 py-2.5"
                data-badge-row
              >
                <BadgeMedallion
                  size="md"
                  :family="badge.family"
                  :tier="badge.tier"
                  :title="badge.title"
                  :description="badge.description"
                />
                <div class="min-w-0 flex-1">
                  <div class="text-base-medium text-ink-gray-9">
                    {{ badge.title }}
                    <span class="font-normal text-ink-gray-5">· {{ badge.tier }}</span>
                  </div>
                  <div class="truncate text-p-sm text-ink-gray-6">{{ badge.description }}</div>
                </div>
                <Switch
                  v-model="badgeSwitches[badge.name]"
                  :aria-label="`${badge.title} (${badge.tier})`"
                  :disabled="saving"
                />
              </li>
            </ul>
          </div>
        </div>
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
import {
  Button,
  Checkbox,
  ErrorMessage,
  Select,
  Switch,
  Textarea,
  TextInput,
  call,
  toast,
} from 'frappe-ui'
import BadgeMedallion from '@/components/Badges/BadgeMedallion.vue'
import LoadError from '@/components/LoadError.vue'
import UserCombobox from '@/components/UserCombobox.vue'
import { BADGE_GROUPS, type BadgeGroup, type BadgeTier } from '@/data/badges'
import { errorText } from '@/utils'

type SettingsBadge = {
  name: string
  title: string
  description: string
  badge_group: BadgeGroup
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
const search = ref('')
const onCount = computed(() => Object.values(badgeSwitches.value).filter(Boolean).length)
// Matches the name, the tier, the group and what the badge is for.
const groups = computed(() => {
  const words = search.value.toLowerCase().split(/\s+/).filter(Boolean)
  const shown = badges.value.filter((badge) => {
    const text =
      `${badge.title} ${badge.tier} ${badge.badge_group} ${badge.description}`.toLowerCase()
    return words.every((word) => text.includes(word))
  })
  return BADGE_GROUPS.map((title) => ({
    title,
    badges: shown.filter((badge) => badge.badge_group === title),
  })).filter((group) => group.badges.length)
})

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
