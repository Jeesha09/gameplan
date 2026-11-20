<template>
  <div class="divide-y divide-outline-gray-1">
    <AdminSettingField
      :id="`admin-setting-${toggle.key}`"
      v-model="draft[toggle.key]"
      :setting="toggle"
      :unsaved="unsaved.includes(toggle.key)"
      data-testid="trust-levels-switch"
    />
  </div>
  <div class="mt-6">
    <Tabs v-if="enabled" v-model="level">
      <TabList variant="underline">
        <TabTrigger
          v-for="(name, index) in LEVEL_NAMES"
          :key="name"
          :value="String(index)"
          :label="name"
        />
      </TabList>
    </Tabs>
    <h2 v-else class="text-lg-semibold text-ink-gray-8">New account limits</h2>
    <div :class="enabled ? 'pt-5' : 'pt-1'">
      <p class="text-p-base text-ink-gray-6">
        <template v-if="!enabled">
          Trust levels are off. These limits still apply to Guests posting in public Spaces.
        </template>
        <template v-else>
          <template v-if="shown === 0">Everyone starts at New when they join. </template>
          <template v-else-if="shown === 4">
            Leader is never earned. A global admin assigns it by hand from Manage users.
          </template>
          {{ levelDescriptions[shown] }}
        </template>
      </p>
      <div v-if="group" class="mt-3 divide-y divide-outline-gray-1">
        <section v-for="part in group.sections" :key="part.title" class="py-5">
          <h3 class="text-base-medium text-ink-gray-8">{{ part.title }}</h3>
          <p v-if="part.description" class="mt-1 text-p-sm text-ink-gray-6">
            {{ part.description }}
          </p>
          <div class="mt-3 grid grid-cols-[repeat(auto-fill,11rem)] items-end gap-x-10 gap-y-5">
            <AdminSettingField
              v-for="[field] in part.fields"
              :id="`admin-setting-${trustPrefix}${field}`"
              :key="field"
              v-model="draft[trustPrefix + field]"
              :setting="settingFor(field)"
              :unsaved="unsaved.includes(trustPrefix + field)"
              field
              type="number"
              :min="ranges[field]?.[0]"
              :max="ranges[field]?.[1]"
            />
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { TabList, TabTrigger, Tabs } from 'frappe-ui'
import AdminSettingField from '@/components/AdminSettings/AdminSettingField.vue'
import { draft } from '@/components/AdminSettings/draft'
import { trustPrefix, type AdminSetting } from '@/components/AdminSettings/sections'
import {
  LEVEL_NAMES,
  SETTING_GROUPS,
  levelDescriptions,
  type LevelNumber,
} from '@/data/trustLevels'

const props = defineProps<{
  settings: AdminSetting[]
  ranges: Record<string, [number, number]>
  unsaved: string[]
}>()

const toggle = computed(() => props.settings.find((s) => s.key === `${trustPrefix}enabled`)!)
const enabled = computed(() => Boolean(draft[toggle.value.key]))
const level = ref('1')
// With levels off only the New limits apply, and only to Guests in public Spaces.
const shown = computed(() => (enabled.value ? Number(level.value) : 0) as LevelNumber)
const group = computed(() => SETTING_GROUPS.find((item) => item.title === LEVEL_NAMES[shown.value]))

function settingFor(field: string) {
  return props.settings.find((s) => s.key === trustPrefix + field)!
}
</script>
