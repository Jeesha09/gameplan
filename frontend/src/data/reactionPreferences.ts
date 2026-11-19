import { computed, ref } from 'vue'
import { debounce, toast, useDoctype } from 'frappe-ui'
import type { GPUserProfile } from '@/types/doctypes'
import { siteSettings } from './siteSettings'

export const quickReactionSlotCount = 20

export const defaultQuickReactionEmojis = ['👍', '😄', '🎉', '❤️', '🙏', '👀']

/**
 * Per-user preference, persisted on GP User Profile. The ref is the source of
 * truth in the client; `loadQuickReactionSlots` seeds it from boot data and any
 * edit is pushed back to the server on a debounce.
 */
const slots = ref<string[]>(normalizeQuickReactionSlots(defaultQuickReactionEmojis))
const profileName = ref('')
const userProfiles = useDoctype<GPUserProfile>('GP User Profile')

/** The 20 reaction slots in order; an empty string marks a free (dotted) slot. */
export const quickReactionSlots = computed(() => slots.value)

/** Configured emoji with empty slots removed — what the reaction picker shows. */
export const currentQuickReactionEmojis = computed(() => slots.value.filter(Boolean))

const persist = debounce((value: string[]) => {
  if (!profileName.value) return
  userProfiles.setValue
    .submit({
      name: profileName.value,
      quick_reaction_emojis: JSON.stringify(normalizeQuickReactionSlots(value)),
    })
    .catch(() => {
      // Best-effort sync; the local ref stays authoritative for this session.
    })
}, 500)

/** Seed slots from persisted boot data without echoing back to the server. */
export function loadQuickReactionSlots(value: unknown, currentProfileName = '') {
  profileName.value = currentProfileName
  slots.value = normalizeQuickReactionSlots(parseStoredSlots(value))
}

function commit(next: string[]) {
  slots.value = normalizeQuickReactionSlots(next)
  persist(slots.value)
}

/** Set (or replace) the emoji in a single slot. Duplicates are rejected. */
export function setQuickReactionEmojiAt(index: number, emoji: string) {
  const next = [...slots.value]
  if (index < 0 || index >= next.length) return
  const trimmed = emoji.trim()
  if (trimmed && next.some((slot, slotIndex) => slotIndex !== index && slot === trimmed)) {
    toast.error(`${trimmed} is already in your quick reactions`)
    return
  }
  next[index] = trimmed
  commit(next)
}

export function moveQuickReactionEmoji(fromIndex: number, toIndex: number) {
  const next = [...slots.value]
  if (fromIndex < 0 || fromIndex >= next.length) return
  const [moved] = next.splice(fromIndex, 1)
  const index = Math.min(Math.max(toIndex, 0), next.length)
  next.splice(index, 0, moved)
  commit(next)
}

export function resetQuickReactionEmojis() {
  commit([...startingQuickReactionEmojis()])
}

export function startingQuickReactionEmojis() {
  return siteSettings.default_quick_reactions.length
    ? siteSettings.default_quick_reactions
    : defaultQuickReactionEmojis
}

function parseStoredSlots(value: unknown): unknown {
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch {
    return null
  }
}

/** Coerce stored data into exactly `quickReactionSlotCount` deduped slots. */
function normalizeQuickReactionSlots(value: unknown): string[] {
  const source = Array.isArray(value) ? value : startingQuickReactionEmojis()

  const seen = new Set<string>()
  const result = source.slice(0, quickReactionSlotCount).map((entry) => {
    const emoji = typeof entry === 'string' ? entry.trim() : ''
    if (!emoji || seen.has(emoji)) return ''
    seen.add(emoji)
    return emoji
  })

  while (result.length < quickReactionSlotCount) result.push('')
  return result
}
