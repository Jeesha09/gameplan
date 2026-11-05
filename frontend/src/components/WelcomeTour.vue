<template>
  <Popover
    v-if="target"
    :key="index"
    trigger="manual"
    :open="true"
    :reference="target"
    :side="mark.side"
    :align="mark.align"
    :offset="8"
    :dismissible="false"
    :autoFocus="false"
    arrow
    bare
  >
    <template #trigger><span class="hidden" /></template>
    <div data-welcome-mark class="w-64 rounded-4 bg-surface-elevation-3 p-3">
      <div class="flex items-start justify-between gap-2">
        <p class="text-base-medium text-ink-gray-8">{{ mark.title }}</p>
        <Button variant="ghost" size="sm" icon="lucide-x" label="Close" @click="close" />
      </div>
      <p class="mt-1 text-p-sm text-ink-gray-6">{{ mark.text }}</p>
      <div class="mt-3 flex items-center justify-between">
        <span class="text-sm text-ink-gray-5">{{ index + 1 }} of {{ marks.length }}</span>
        <Button variant="solid" size="sm" :loading="moving" @click="show(index + 1)">
          {{ index === marks.length - 1 ? 'Done' : 'Next' }}
        </Button>
      </div>
    </div>
  </Popover>
</template>

<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Popover } from 'frappe-ui'
import { showCommunitiesSettings } from '@/components/Settings'
import { activeCommunities, availableCommunities } from '@/data/communities'
import { communityState } from '@/data/communityState'
import { useSessionUser } from '@/data/users'
import { markTourSeen, openTourIfNew, showTour } from '@/data/welcome'

type Mark = {
  target: string
  side: 'top' | 'right' | 'bottom' | 'left'
  align?: 'start' | 'center' | 'end'
  title: string
  text: string
  opensDiscussion?: boolean
  inSettings?: boolean
}

const marks: Mark[] = [
  {
    target: '[data-coach="account"]',
    side: 'right',
    align: 'end',
    title: 'Join communities',
    text: 'Start here: open your account menu, then Settings.',
  },
  {
    target: '[data-coach="settings-communities"]',
    side: 'right',
    title: 'Settings',
    text: 'Open Communities to see everything you can join.',
    inSettings: true,
  },
  {
    target: '[data-coach="community-list"]',
    side: 'left',
    align: 'start',
    title: 'Join',
    text: 'Join as many as you want to follow, then press Next. You can leave from here too.',
    inSettings: true,
  },
  {
    target: '[data-coach="communities"] > *',
    side: 'right',
    align: 'start',
    title: 'Communities',
    text: 'Your old categories are here.',
  },
  {
    target: '[data-coach="spaces"] > *',
    side: 'right',
    align: 'start',
    title: 'Spaces',
    text: 'Sub-categories are here. Pin a favourite from its menu.',
  },
  {
    target: '[data-coach="rail-shortcuts"]',
    side: 'right',
    title: 'Shortcuts',
    text: 'Search, People, Notifications and Drafts.',
  },
  {
    target: '[data-coach="add-new"] > *',
    side: 'bottom',
    align: 'end',
    title: 'Start a discussion',
    text: 'You pick the Space while writing.',
  },
  {
    target: '[data-coach="bell"] button',
    side: 'bottom',
    align: 'end',
    title: 'Notifications',
    text: 'Mute, Mentions only or Watch, close to the old tracking levels.',
    opensDiscussion: true,
  },
  {
    target: '[data-coach="reactions"] button',
    side: 'top',
    align: 'start',
    title: 'Reactions',
    text: 'Old likes are 👍 here. Bookmarks are in the ⋯ menu.',
  },
]

const route = useRoute()
const router = useRouter()
const sessionUser = useSessionUser()
const index = ref(0)
const moving = ref(false)
const target = shallowRef<Element>()
const mark = computed(() => marks[index.value])
let openedDiscussion = false
let openedSettings = false

const HIGHLIGHT = ['ring-2', 'ring-outline-gray-4', 'rounded-[7px]']

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

function isOnScreen(item: Element) {
  const { top, bottom } = item.getBoundingClientRect()
  return top >= 0 && bottom <= window.innerHeight
}

async function waitFor(selector: string) {
  for (let tries = 0; tries < 50; tries++) {
    const items = [...document.querySelectorAll(selector)].filter(
      (item) => item.getClientRects().length > 0,
    )
    const element = items.find(isOnScreen)
    if (element) return element
    if (items.length && tries === 5) items[0].scrollIntoView({ block: 'center' })
    await wait(100)
  }
}

async function waitForPageToSettle() {
  let lastTop: number | undefined
  let stillChecks = 0
  for (let tries = 0; tries < 80 && stillChecks < 8; tries++) {
    const top = document.querySelector('[data-coach="reactions"]')?.getBoundingClientRect().top
    stillChecks = top !== undefined && top === lastTop ? stillChecks + 1 : 0
    lastTop = top
    await wait(100)
  }
}

function pointAt(element?: Element) {
  target.value?.classList.remove(...HIGHLIGHT)
  element?.classList.add(...HIGHLIGHT)
  target.value = element
}

async function leaveSettings() {
  openedSettings = false
  const joined = activeCommunities.value.map((community) => community.name)
  const landing = joined.includes(communityState.id ?? '') ? communityState.id : joined[0]
  if (!landing) return false
  communityState.change(landing)
  await router.push({ name: 'Discussions', params: { communityId: landing } })
  return true
}

async function show(from: number) {
  moving.value = true
  for (let i = from; i < marks.length; i++) {
    if (marks[i].inSettings && !openedSettings) {
      openedSettings = true
      showCommunitiesSettings()
    }
    if (!marks[i].inSettings && openedSettings && !(await leaveSettings())) break
    if (marks[i].opensDiscussion) {
      const link = await waitFor('a[href*="/discussion/"]')
      if (!(link instanceof HTMLElement)) continue
      openedDiscussion = true
      link.click()
      await waitForPageToSettle()
    }
    const element = await waitFor(marks[i].target)
    if (element) {
      index.value = i
      pointAt(element)
      moving.value = false
      return
    }
  }
  moving.value = false
  close()
}

function close() {
  showTour.value = false
}

watch(showTour, (open) => {
  if (open) {
    show(0)
    return
  }
  pointAt()
  markTourSeen()
  if (openedDiscussion) router.back()
  openedDiscussion = false
  openedSettings = false
})

watch(
  () => route.name,
  (name) => {
    if (!showTour.value || moving.value) return
    const onSettings = String(name).startsWith('Settings')
    if (openedSettings && onSettings) return
    if (openedSettings) {
      show(marks.findIndex((item, i) => i > index.value && !item.inSettings))
      return
    }
    openedDiscussion = false
    close()
  },
)

watch(
  () => availableCommunities.value.length > 0,
  (ready) => {
    if (ready && !sessionUser.isGuest) openTourIfNew()
  },
  { immediate: true },
)
</script>

<style>
[data-slot='content']:has([data-welcome-mark]) {
  filter: drop-shadow(0 0 1px var(--outline-gray-3)) drop-shadow(0 6px 14px rgb(0 0 0 / 0.12));
}

[data-slot='content']:has([data-welcome-mark]) [data-slot='arrow'] {
  width: 8px;
  height: 4px;
  fill: var(--surface-elevation-3);
}

[data-coach='community-list'].ring-2 {
  position: relative;
  box-shadow: none;
}

[data-coach='community-list'].ring-2::after {
  content: '';
  position: absolute;
  inset: 0 -8px -8px;
  z-index: 20;
  border: 2px solid var(--outline-gray-4);
  border-radius: 7px;
  pointer-events: none;
}

body:has([data-welcome-mark]) [data-slot='content']:has([data-slot='bubble']) {
  display: none;
}
</style>
