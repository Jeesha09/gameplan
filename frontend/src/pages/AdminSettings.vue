<template>
  <PageHeaderMobile v-if="!panelOwnsPageHeader" class="sm:hidden" :title="section.label">
    <template #prefix><PageHeaderBackButton :fallback-route="{ name: 'More' }" /></template>
    <template v-if="pageChanges.length" #suffix>
      <Button variant="solid" :loading="saving" @click="saveChanges">Save</Button>
    </template>
  </PageHeaderMobile>
  <PageHeader class="hidden sm:flex">
    <div class="flex min-w-0 items-center gap-3">
      <Breadcrumbs class="h-7" :items="crumbs" />
    </div>
    <div v-if="pageChanges.length" class="flex shrink-0 items-center gap-2">
      <Button :disabled="saving" @click="discardChanges(pageChanges)">Discard</Button>
      <Button variant="solid" :loading="saving" @click="saveChanges">Save</Button>
    </div>
  </PageHeader>
  <div class="flex min-h-0 flex-1 flex-col text-ink-gray-9 sm:flex-row">
    <Teleport v-if="!isMobileViewport" to="#admin-settings-sidebar">
      <Sidebar
        :collapsible="false"
        width="14rem"
        aria-label="Admin settings pages"
        class="hidden sm:flex"
      >
        <SidebarHeader title="Admin settings" :show-logo="false" />
        <ScrollArea class="min-h-0 flex-1" viewport-class="px-2 pt-2 pb-10">
          <div class="space-y-0.5">
            <SidebarItem
              v-for="item in adminSections"
              :key="item.id"
              :label="item.label"
              :icon="item.icon"
              :active="section.id === item.id"
              @click="open(item.id)"
            >
              <template v-if="sectionHasChanges(item)" #suffix>
                <span
                  class="mr-2 size-1.5 rounded-full bg-surface-gray-7"
                  aria-label="Unsaved changes"
                />
              </template>
            </SidebarItem>
          </div>
        </ScrollArea>
      </Sidebar>
    </Teleport>
    <div v-if="!panelOwnsPageHeader" class="border-b border-outline-gray-2 p-4 sm:hidden">
      <Select
        :model-value="section.id"
        aria-label="Admin settings page"
        :options="adminSections.map((item) => ({ label: item.label, value: item.id }))"
        @update:model-value="(id) => open(String(id))"
      />
    </div>
    <div v-if="section.id === 'communities'" class="flex min-h-0 min-w-0 flex-1 flex-col">
      <CommunitiesSettings />
    </div>
    <ScrollArea v-else ref="scrollArea" class="min-h-0 min-w-0 flex-1" viewport-class="py-5">
      <div class="body-container pb-16">
        <AdminUsers v-if="section.id === 'users'" />
        <AccountSuspensions v-else-if="section.id === 'account-restrictions'" />
        <BadgeSettings v-else-if="section.id === 'badges'" />
        <div v-else class="space-y-8">
          <div
            v-for="(group, index) in groups"
            :key="group.heading || group.title || index"
            :class="{ 'pt-8': group.heading && index }"
          >
            <h1 v-if="group.heading" class="mb-4 text-xl-semibold text-ink-gray-9">
              {{ group.heading }}
            </h1>
            <h2 v-if="group.title" class="text-md-semibold text-ink-gray-8">
              {{ group.title }}
            </h2>
            <div v-if="group.layout === 'identity'" class="grid gap-6">
              <AdminSettingField
                v-for="setting in group.settings.filter((s) => s.type !== 'image')"
                :id="`admin-setting-${setting.key}`"
                :key="setting.key"
                v-model="values[setting.key]"
                :setting="setting"
                :unsaved="pageChanges.includes(setting.key)"
                field
              />
              <div class="divide-y divide-outline-gray-1">
                <AdminSettingField
                  v-for="setting in group.settings.filter((s) => s.type === 'image')"
                  :id="`admin-setting-${setting.key}`"
                  :key="setting.key"
                  v-model="values[setting.key]"
                  :setting="setting"
                  @save="saveImage(setting)"
                />
              </div>
            </div>
            <div v-else-if="group.layout === 'fields'" class="grid gap-6 pt-2 sm:grid-cols-2">
              <AdminSettingField
                v-for="setting in group.settings"
                :id="`admin-setting-${setting.key}`"
                :key="setting.key"
                v-model="values[setting.key]"
                :setting="setting"
                :unsaved="pageChanges.includes(setting.key)"
                field
                @save="saveImage(setting)"
              />
            </div>
            <div v-else class="divide-y divide-outline-gray-1" :class="{ 'mt-2': group.title }">
              <AdminSettingField
                v-for="setting in group.settings.filter((s) => !s.inline)"
                :id="`admin-setting-${setting.key}`"
                :key="setting.key"
                v-model="values[setting.key]"
                :max="setting.max && values[setting.max]"
                @update:max="(value: number) => (values[setting.max!] = value)"
                :setting="setting"
                :unsaved="
                  pageChanges.includes(setting.key) ||
                  (!!setting.max && pageChanges.includes(setting.max))
                "
                :class="{
                  'ml-1 !border-t-0 border-l border-outline-gray-2 !py-2.5 pl-4': setting.parent,
                }"
                @save="saveImage(setting)"
              />
            </div>
          </div>
        </div>
      </div>
    </ScrollArea>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, onMounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Breadcrumbs,
  Button,
  PageHeader,
  PageHeaderBackButton,
  PageHeaderMobile,
  ScrollArea,
  Select,
  Sidebar,
  SidebarHeader,
  SidebarItem,
  call,
  toast,
} from 'frappe-ui'
import AdminSettingField from '@/components/AdminSettings/AdminSettingField.vue'
import {
  adminSections,
  postingLimitPrefix,
  type AdminSetting,
} from '@/components/AdminSettings/sections'
import AccountSuspensions from '@/components/AccountSuspensions.vue'
import AdminUsers from '@/components/AdminSettings/AdminUsers.vue'
import BadgeSettings from '@/components/BadgeSettings.vue'
import {
  discardChanges,
  dirtyKeys,
  draft,
  loadSaved,
  markSaved,
} from '@/components/AdminSettings/draft'
import { panelAsPage, panelOwnsPageHeader } from '@/components/Settings'
import CommunitiesSettings from '@/components/Settings/CommunitiesSettings.vue'
import { getCommunity } from '@/data/communities'
import { defaultQuickReactionEmojis } from '@/data/reactionPreferences'
import { applyFavicon, siteSettings, type SiteSettings } from '@/data/siteSettings'
import { extractServerMessage } from '@/utils'
import { useIsMobile } from '@/utils/useIsMobile'

const route = useRoute()
const router = useRouter()
const isMobileViewport = useIsMobile()
const scrollArea = ref<{ viewportElement: HTMLElement | null }>()
provide(panelAsPage, true)

const section = computed(
  () => adminSections.find((item) => item.id === route.query.tab) || adminSections[0],
)

const communityId = computed(() =>
  section.value.id === 'communities' && route.query.community ? String(route.query.community) : '',
)

function communityViewRoute(view: 'spaces' | 'members') {
  return {
    name: 'AdminSettings',
    query: { tab: 'communities', community: communityId.value, view },
  }
}

const crumbs = computed(() => {
  if (!communityId.value) return [{ label: section.value.label }]
  return [
    { label: 'Communities', route: { name: 'AdminSettings', query: { tab: 'communities' } } },
    {
      label: getCommunity(communityId.value)?.title || 'Community',
      route: communityViewRoute('spaces'),
    },
  ]
})


function open(id: string) {
  router.replace({ name: 'AdminSettings', query: { tab: id } })
}

const values = draft

function sectionHasChanges(item: (typeof adminSections)[number]) {
  return item.groups.some((group) => group.settings.some((s) => dirtyKeys.value.includes(s.key)))
}

const pageChanges = computed(() => {
  const keys = new Set(section.value.groups.flatMap((group) => group.settings.map((s) => s.key)))
  return dirtyKeys.value.filter((key) => keys.has(key))
})

const groups = computed(() =>
  section.value.groups.map((group) => ({
    ...group,
    settings: group.settings.filter((setting) => !setting.parent || values[setting.parent]),
  })),
)

const postingLimitKeys = Object.keys(values).filter((key) => key.startsWith(postingLimitPrefix))

async function loadPostingLimits() {
  try {
    const policy = await call<Record<string, number>>('gameplan.posting_limits.settings')
    for (const key of postingLimitKeys) {
      const value = policy[key.slice(postingLimitPrefix.length)]
      loadSaved(key, key.endsWith('_enabled') ? Boolean(value) : value)
    }
  } catch (error) {
    toast.error(extractServerMessage(error) || 'Could not load posting limits')
  }
}

const siteKeys = new Set<string>()

async function loadSiteSettings() {
  try {
    const settings = await call<Record<string, any>>('gameplan.site_settings.get_settings')
    for (const [key, value] of Object.entries(settings)) {
      siteKeys.add(key)
      const builtIn = key === 'default_quick_reactions' && !value.length
      loadSaved(key, builtIn ? [...defaultQuickReactionEmojis] : value)
    }
  } catch (error) {
    toast.error(extractServerMessage(error) || 'Could not load settings')
  }
}

function serverValue(key: string) {
  const value = values[key]
  if (key === 'default_quick_reactions') {
    return JSON.stringify(value) === JSON.stringify(defaultQuickReactionEmojis) ? [] : value
  }
  return value
}

function applyToApp(key: string) {
  if (!(key in siteSettings)) return
  const current = siteSettings[key as keyof SiteSettings]
  const value = serverValue(key)
  Object.assign(siteSettings, { [key]: typeof current === 'number' ? Number(value) || 0 : value })
  if (key === 'favicon') applyFavicon()
}

async function saveImage(setting: AdminSetting) {
  try {
    await call('gameplan.site_settings.save_settings', {
      values: { [setting.key]: values[setting.key] },
    })
    markSaved([setting.key])
    applyToApp(setting.key)
    toast.success(`${setting.label} saved`)
  } catch (error) {
    toast.error(extractServerMessage(error) || `Could not save ${setting.label}`)
  }
}

const saving = ref(false)

async function saveChanges() {
  const changed = [...pageChanges.value]
  const site = changed.filter((key) => siteKeys.has(key))
  const posting = changed.filter((key) => key.startsWith(postingLimitPrefix))
  const other = changed.filter((key) => !site.includes(key) && !posting.includes(key))
  saving.value = true
  try {
    if (site.length) {
      await call('gameplan.site_settings.save_settings', {
        values: Object.fromEntries(site.map((key) => [key, serverValue(key)])),
      })
      markSaved(site)
      site.forEach(applyToApp)
    }
    if (posting.length) {
      await call(
        'gameplan.posting_limits.save_settings',
        Object.fromEntries(
          postingLimitKeys.map((key) => [
            key.slice(postingLimitPrefix.length),
            Number(values[key]) || 0,
          ]),
        ),
      )
      markSaved(posting)
    }
    markSaved(other)
    toast.success('Changes saved')
  } catch (error) {
    toast.error(extractServerMessage(error) || 'Could not save changes')
  } finally {
    saving.value = false
  }
}

async function revealSetting() {
  const key = route.query.setting
  if (!key) return
  await nextTick()
  document.getElementById(`admin-setting-${key}`)?.scrollIntoView({ block: 'center' })
  router.replace({ name: 'AdminSettings', query: { tab: section.value.id } })
}

watch(
  () => route.query.tab,
  () => scrollArea.value?.viewportElement?.scrollTo({ top: 0 }),
)
watch(() => route.query.setting, revealSetting)
onMounted(() => {
  revealSetting()
  loadPostingLimits()
  loadSiteSettings()
})
</script>
