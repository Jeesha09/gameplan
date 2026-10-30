import { computed, reactive, readonly, ref, watch } from 'vue'
import { call, debounce, useCall } from 'frappe-ui'
import router from '@/router'
import { setCommunityOrder } from './communityOrder'
import {
  loadNotificationPreferences,
  type NotificationChannel,
  type ParticipationLevel,
} from './notificationPreferences'
import { loadPinnedSpaces } from './pinnedSpaces'
import { loadQuickReactionSlots } from './reactionPreferences'
import { setSidebarBadgeStyle, type SidebarBadgeStyle } from './sidebarPreferences'
import { session } from './session'
import { onSocketEvent } from '@/socket'
import { isAnonymousVisitor } from '@/utils/publicAccess'
import { getSessionUserFromCookie } from '@/utils/sessionCookie'

export type EmailDigestFrequency = 'Off' | 'Weekly' | 'Fortnightly' | 'Monthly'
export type EmailDigestDayOfWeek =
  | 'Monday'
  | 'Tuesday'
  | 'Wednesday'
  | 'Thursday'
  | 'Friday'
  | 'Saturday'
  | 'Sunday'

let usersByName = reactive<Record<string, UserInfo>>({})

export interface UserInfo {
  banned_communities?: string[]
  name: string
  email: string
  enabled: number
  user_image: string
  full_name: string
  user_type: string
  /** Frappe's own User.time_zone; the schedule in Settings → Notifications runs in it. */
  time_zone?: string | null
  creation: string
  user_profile: string
  image_background_color: string
  is_image_background_removed: number
  discussions_count_3m: number
  comments_count_3m: number
  community_order?: unknown
  pinned_spaces?: unknown
  quick_reaction_emojis?: unknown
  sidebar_badge_style?: SidebarBadgeStyle
  email_digest_frequency?: EmailDigestFrequency
  email_digest_day_of_week?: EmailDigestDayOfWeek
  email_digest_last_sent_on?: string
  participation_level?: ParticipationLevel
  notification_channel?: NotificationChannel
  receive_notifications?: 0 | 1
  active_hours_enabled?: 0 | 1
  active_hours_start?: string
  active_hours_end?: string
  active_hours_days?: string
  bio: string
  role: 'Gameplan Admin' | 'Gameplan Member' | 'Gameplan Guest'
  isGuest?: boolean
  isNotGuest?: boolean
  isDisabled?: boolean
  /**
   * True for a record `useUser` invented because the id is not in the store — either the
   * user list has not loaded yet, or the user is not in it at all (`get_user_info` only
   * returns users holding a Gameplan role). Its `full_name` is a guess (the local part of
   * the email), so callers with a better name of their own should prefer theirs.
   */
  isPlaceholder?: boolean
}

function mergeUserInfo(user: UserInfo) {
  user.isGuest = user.role === 'Gameplan Guest'
  user.isNotGuest = !user.isGuest
  user.isDisabled = user.enabled === 0
  // Set explicitly (not just left undefined) so merging a real record over a placeholder
  // already in the store clears the flag — `Object.assign` only copies keys it has.
  user.isPlaceholder = false
  const existing = usersByName[user.name]
  if (existing) {
    Object.assign(existing, user)
  } else {
    usersByName[user.name] = user
  }
  if (user.name === session.user) {
    setCommunityOrder(user.community_order)
    loadPinnedSpaces(user.pinned_spaces, user.user_profile)
    loadQuickReactionSlots(user.quick_reaction_emojis, user.user_profile)
    setSidebarBadgeStyle(user.sidebar_badge_style)
    loadNotificationPreferences(user)
  }
}

export let users = useCall<UserInfo[]>({
  url: '/api/v2/method/gameplan.api.get_user_info',
  params: () => ({ user: getSessionUserFromCookie() }),
  cacheKey: 'SessionUser',
  initialData: [],
  transform(data) {
    for (let user of data) {
      mergeUserInfo(user)
    }
    return data
  },
  onError(error) {
    if (error && error.type === 'AuthenticationError') {
      let { pathname, search, hash } = window.location
      window.location.href = '/login?redirect-to=' + encodeURIComponent(pathname + search + hash)
    }
  },
  immediate: false,
})

const firstFetchSettled = ref(false)

/**
 * True once the first `get_user_info` request has SETTLED — succeeded or failed — and
 * never false again. It is `users.isFinished`, latched.
 *
 * Anything that renders the app shell must gate on this and NOT on `users.isFinished`
 * directly. `isFinished` only means "no request in flight", so it flips back to false on
 * every reload, and a profile edit anywhere broadcasts `gameplan:users_changed`, which
 * reloads this list mid-session. Gating on it unmounts the whole layout and any open
 * dialog for the length of that refetch: the app visibly blanks out. A refetch must never
 * unmount anything.
 *
 * Settle, not success, is deliberate. A failed load (500, offline, permission error) has
 * to leave the app mounted and degraded, the way `isFinished` did. Latching on success
 * only would leave the shell unmounted forever after one bad response — a permanently
 * blank page, which is worse than the bug being fixed here.
 */
export const usersReady = readonly(firstFetchSettled)

/**
 * Start the app without the user list, for someone who is not signed in. `get_user_info`
 * is closed to them; the authors on a public page are looked up one by one instead (see
 * `requestPublicProfile`).
 */
export function settleUsersWithoutFetching() {
  firstFetchSettled.value = true
}

// Latched from `isFinished` rather than from the onSuccess/onError hooks so it cannot
// drift from what "the request has settled" means: onSuccess is skipped for a response
// with no body, which would strand the flag at false. Never stopped, by design — this
// module lives as long as the app.
watch(
  () => users.isFinished,
  (isFinished) => {
    if (isFinished) firstFetchSettled.value = true
  },
  { immediate: true },
)

// A profile edit changes what everyone else renders (avatar, name, role), so the backend
// broadcasts this to every session. Skipped until the first fetch has settled: `users` is
// `immediate: false` and App.vue fetches it once the session is known, and reloading before
// that would race that first fetch on the same instance. After a failed first fetch this
// does allow a reload, which is wanted — it is the one path that can recover the list.
onSocketEvent('gameplan:users_changed', (payload) => {
  if (!usersReady.value || isAnonymousVisitor()) return
  if (!payload?.profiles) {
    users.reload()
    return
  }
  const profiles = new Set(payload.profiles)
  for (const user of Object.values(usersByName)) {
    if (!user.isPlaceholder && profiles.has(user.user_profile)) refetchUser(user.name)
  }
})

export function updateUserInfo(user: UserInfo) {
  mergeUserInfo(user)
  const listedUser = users.data?.find((item) => item.name === user.name)
  if (listedUser) Object.assign(listedUser, user)
}

const requestedUsers = new Set<string>()
const pendingUsers = new Set<string>()
let userBatchTimer: number | null = null

function requestUser(name: string) {
  if (requestedUsers.has(name)) return
  requestedUsers.add(name)
  pendingUsers.add(name)
  userBatchTimer ??= window.setTimeout(fetchPendingUsers, 0)
}

export function refetchUser(name: string) {
  requestedUsers.delete(name)
  requestUser(name)
}

async function fetchPendingUsers() {
  userBatchTimer = null
  const names = [...pendingUsers].slice(0, 100)
  names.forEach((name) => pendingUsers.delete(name))
  if (pendingUsers.size) userBatchTimer = window.setTimeout(fetchPendingUsers, 0)
  try {
    const rows = await call<UserInfo[]>('gameplan.api.get_user_info', { users: names })
    rows.forEach(mergeUserInfo)
  } catch (error) {
    names.forEach((name) => requestedUsers.delete(name))
    console.error('Could not load users', error)
  }
}

export interface UserSearchParams {
  query?: string
  start?: number
  limit?: number
  order_by?: 'relevance' | 'full_name' | 'creation' | 'role'
  descending?: boolean
  include_guests?: boolean
  include_disabled?: boolean
  community?: string
  exclude_community?: string
  exclude_space?: string | number
}

export async function searchUsers(params: UserSearchParams = {}): Promise<UserInfo[]> {
  const rows = await call<UserInfo[]>('gameplan.api.search_users', params)
  rows.forEach(mergeUserInfo)
  return rows.map((row) => usersByName[row.name])
}

export function useUserSearch(params: () => UserSearchParams | null, wait = 250) {
  const results = ref<UserInfo[]>([])
  const loading = ref(false)
  let request = 0

  async function run(current: number, value: UserSearchParams) {
    try {
      const rows = await searchUsers(value)
      if (current === request) results.value = rows
    } catch (error) {
      if (current === request) results.value = []
      console.error('Could not search users', error)
    } finally {
      if (current === request) loading.value = false
    }
  }
  const runDebounced = debounce(run, wait)

  function reload() {
    const value = params()
    const current = ++request
    if (!value) {
      loading.value = false
      return
    }
    loading.value = true
    runDebounced(current, value)
  }

  watch(params, reload, { immediate: true, deep: true })
  return { results, loading, reload }
}

const memberCountCall = useCall<number>({
  url: '/api/v2/method/gameplan.api.get_member_count',
  cacheKey: 'MemberCount',
  immediate: false,
})

/** How many people the People page lists: enabled accounts, guests excluded. */
export const memberCount = computed(() => memberCountCall.data ?? 0)

export function loadMemberCount() {
  memberCountCall.reload()
}

// Shared so `useUser('')` is referentially stable across renders, and never lands in
// `usersByName` (its key would be the empty string and the next unknown actor would
// inherit whatever the last one merged into it).
const unknownUser = getPlaceholderUser('', 'Unknown')

/**
 * Resolve a user id to its `UserInfo`, or to a placeholder (`isPlaceholder`) when the id
 * is not in the store — the user list is still loading, or the user is not in it at all.
 *
 * "The session user" is what *calling it with no arguments* means, plus the explicit
 * `'sessionUser'` sentinel. Any id that is actually passed resolves to that id, and an
 * empty, `null` or `undefined` one resolves to the shared Unknown placeholder — never to
 * the session user. That is why the sentinel is an arity check and not a parameter
 * default: a default also fires for an explicitly passed `undefined`, which is how the
 * viewer's own name ended up rendered as the actor on someone else's activity whenever
 * the actor field came back empty.
 */
export function useUser(...args: [] | [email: string | null | undefined]): UserInfo {
  let email = args.length === 0 ? session.user : args[0]
  if (email === 'sessionUser') {
    email = session.user
  }
  if (!email) return unknownUser
  if (!usersByName[email]) {
    usersByName[email] = getPlaceholderUser(email, email.split('@')[0])
  }
  if (usersByName[email].isPlaceholder) {
    if (isAnonymousVisitor()) requestPublicProfile(email)
    else if (session.isLoggedIn) requestUser(email)
  }
  return usersByName[email]
}

// For someone who is not signed in, a user id is a profile handle (the server never sends
// them an email address). Each handle seen is looked up once, batched per tick, and the
// name and avatar merged into its placeholder. A handle the server will not describe (its
// owner wrote nothing public) keeps the placeholder.
const requestedHandles = new Set<string>()
const pendingHandles = new Set<string>()
let publicProfileTimer: number | null = null

function requestPublicProfile(handle: string) {
  if (requestedHandles.has(handle)) return
  requestedHandles.add(handle)
  pendingHandles.add(handle)
  publicProfileTimer ??= window.setTimeout(fetchPublicProfiles, 0)
}

interface PublicProfile {
  handle: string
  full_name: string
  image: string | null
  image_background_color: string | null
  is_image_background_removed: number
}

async function fetchPublicProfiles() {
  publicProfileTimer = null
  // Match the server's 100-profile cap without dropping the rest of a long thread.
  const handles = [...pendingHandles].slice(0, 100)
  handles.forEach((handle) => pendingHandles.delete(handle))
  await fetchPublicProfileBatch(handles)
  if (pendingHandles.size) publicProfileTimer ??= window.setTimeout(fetchPublicProfiles, 0)
}

async function fetchPublicProfileBatch(handles: string[]) {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const profiles = await call<PublicProfile[]>('gameplan.api.get_public_user_info', { handles })
      for (const profile of profiles) {
        Object.assign(usersByName[profile.handle] ?? useUser(profile.handle), {
          full_name: profile.full_name,
          user_image: profile.image || '',
          image_background_color: profile.image_background_color || '',
          is_image_background_removed: profile.is_image_background_removed || 0,
          user_profile: profile.handle,
          isPlaceholder: false,
        })
      }
      return
    } catch (error) {
      if (attempt === 2) {
        handles.forEach((handle) => requestedHandles.delete(handle))
        console.error('Could not load public profiles', error)
      } else {
        await new Promise((resolve) => window.setTimeout(resolve, 1000 * (attempt + 1)))
      }
    }
  }
}

function getPlaceholderUser(email: string, full_name: string) {
  return {
    name: email,
    email: email,
    full_name: full_name,
    isPlaceholder: true,
    user_image: '',
    role: 'Gameplan Member',
    enabled: 1,
    user_profile: '',
    image_background_color: '',
    is_image_background_removed: 0,
    user_type: 'Website User',
  } as UserInfo
}

export function useSessionUser() {
  return useUser('sessionUser')
}

export function isGameplanAdmin(user: UserInfo = useSessionUser()) {
  return user.name === 'Administrator' || user.role === 'Gameplan Admin'
}
