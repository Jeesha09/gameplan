<template>
  <div class="text-ink-gray-9">
    <LoadError
      v-if="loadError"
      :message="errorText(loadError, 'Could not load the badge settings.')"
      @retry="load"
    />
    <template v-else-if="loaded">
      <section>
        <div class="flex items-start justify-between gap-4">
          <div>
            <span class="text-base-medium leading-tighter block text-ink-gray-8">
              Use badges<span v-if="changed('enabled')" class="unsaved-dot" aria-hidden="true" />
            </span>
            <p class="mt-1 text-base leading-5 text-ink-gray-6">
              Members earn badges as they take part. Turning badges on works out everyone's badges
              in the background, without notifying anyone. Members see the change after reloading
              the page.
            </p>
          </div>
          <Switch v-model="enabled" aria-label="Use badges" />
        </div>
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
            <div class="flex items-center justify-between pb-1.5 pr-[13px]">
              <h3 class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">
                {{ group.title }}
              </h3>
              <span class="flex items-center gap-2 text-p-sm text-ink-gray-7">
                Select all
                <Checkbox
                  :model-value="allOn(group.badges)"
                  :indeterminate="someOn(group.badges)"
                  :aria-label="`Select all ${group.title} badges`"
                  @update:model-value="setMany(group.badges, Boolean($event))"
                />
              </span>
            </div>
            <ul class="divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2">
              <li
                v-for="badge in group.badges"
                :key="badge.name"
                class="flex items-center gap-3 px-3 py-2.5"
                data-badge-row
              >
                <BadgeMedallion
                  size="md"
                  :tooltip="false"
                  :family="badge.family"
                  :tier="badge.tier"
                  :title="badge.title"
                  :description="badge.description"
                />
                <div class="min-w-0 flex-1">
                  <div class="text-base-medium text-ink-gray-9">
                    {{ badge.title }}
                    <span class="font-normal text-ink-gray-5">· {{ badge.tier }}</span
                    ><span v-if="changed(badge.name)" class="unsaved-dot" aria-hidden="true" />
                  </div>
                  <div class="truncate text-p-sm text-ink-gray-6">{{ badge.description }}</div>
                </div>
                <Checkbox
                  :model-value="isOn(badge.name)"
                  :aria-label="`${badge.title} (${badge.tier})`"
                  @update:model-value="setMany([badge], Boolean($event))"
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
import { draft, loadSaved, savedValue } from '@/components/AdminSettings/draft'
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
  loadError = ref<unknown>(null)
const badges = ref<SettingsBadge[]>([])
const search = ref('')

// The switches live in the page's shared draft, which the header's Save and Discard commit.
type BadgesDraft = { enabled: boolean; disabled: string[] }
const current = computed(() => draft.badges as BadgesDraft)
const enabled = computed({
  get: () => current.value.enabled,
  set: (on: boolean) => (draft.badges = { ...current.value, enabled: on }),
})
const isOn = (name: string) => !current.value.disabled.includes(name)
// Turns several badges on or off at once, for one row or a whole group.
function setMany(list: SettingsBadge[], on: boolean) {
  const names = new Set(list.map((badge) => badge.name))
  const others = current.value.disabled.filter((name) => !names.has(name))
  draft.badges = { ...current.value, disabled: on ? others : [...others, ...names] }
}
const allOn = (list: SettingsBadge[]) => list.every((badge) => isOn(badge.name))
// A mix: some on and some off. All on or all off is not.
const someOn = (list: SettingsBadge[]) => !allOn(list) && list.some((badge) => isOn(badge.name))
// A dot beside what differs from what is saved, as on the other pages.
function changed(what: 'enabled' | string) {
  const saved = savedValue('badges') as BadgesDraft
  if (what === 'enabled') return saved.enabled !== current.value.enabled
  return saved.disabled.includes(what) !== current.value.disabled.includes(what)
}

const onCount = computed(() => badges.value.filter((badge) => isOn(badge.name)).length)
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
    .filter((badge) => isOn(badge.name))
    .map((badge) => ({ label: badge.title, value: badge.name })),
)
const canChange = computed(
  () =>
    Boolean(person.value && chosenBadge.value && reason.value.trim()) &&
    !badges.value.find((badge) => badge.name === chosenBadge.value)?.per_post,
)

async function load() {
  loadError.value = null
  try {
    const settings = await call<Settings>('gameplan.badges.api.get_settings')
    badges.value = settings.badges
    loadSaved('badges', {
      enabled: Boolean(settings.enabled),
      disabled: settings.badges.filter((badge) => !badge.enabled).map((badge) => badge.name),
    })
    loaded.value = true
  } catch (error) {
    loadError.value = error
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
<style scoped>
.unsaved-dot {
  @apply ml-1.5 inline-block size-1.5 rounded-full bg-surface-gray-7 align-middle;
}
</style>
