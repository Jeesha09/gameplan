import { computed, reactive } from 'vue'
import { adminSections } from './sections'

function copy<T>(value: T): T {
  return Array.isArray(value) ? ([...value] as T) : value
}

function defaults() {
  return Object.fromEntries(
    adminSections.flatMap((section) =>
      section.groups.flatMap((group) =>
        group.settings.map((setting) => [setting.key, copy(setting.default)]),
      ),
    ),
  )
}

function comparable(value: unknown) {
  return JSON.stringify(value ?? null, (_, item) =>
    typeof item === 'number' ? String(item) : item,
  )
}

export const draft = reactive<Record<string, any>>(defaults())
const saved = reactive<Record<string, any>>(defaults())

export const dirtyKeys = computed(() =>
  Object.keys(draft).filter((key) => comparable(draft[key]) !== comparable(saved[key])),
)
export const hasUnsavedChanges = computed(() => dirtyKeys.value.length > 0)

export function loadSaved(key: string, value: unknown) {
  const untouched = !dirtyKeys.value.includes(key)
  saved[key] = copy(value)
  if (untouched) draft[key] = copy(value)
}

export function markSaved(keys: string[]) {
  for (const key of keys) saved[key] = copy(draft[key])
}

export function discardChanges(keys: string[]) {
  for (const key of keys) draft[key] = copy(saved[key])
}

window.addEventListener('beforeunload', (event) => {
  if (hasUnsavedChanges.value) event.preventDefault()
})
