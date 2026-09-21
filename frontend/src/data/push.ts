import { toast } from 'frappe-ui'
import { captureError } from '@/utils/errorReporting'

/**
 * Push on this device — the browser side of the Push channel.
 *
 * A push is delivered by the browser maker's service (Firebase Cloud Messaging), so the
 * server needs this browser's address there: the "token". Firebase's library is used for
 * exactly that one job, minting the token, and is loaded only when someone turns push on.
 * The address goes to the server (`frappe.push_notification.subscribe`), which hands it to
 * the Push Notification Relay; from then on `gameplan/notifications/push.py` can reach this
 * device. A small background script (`firebase-messaging-sw.js`) shows the popup when the
 * tab is closed.
 *
 * The same shape as Raven's web client (the reference Frappe app for push); in-app
 * notifications keep coming over the realtime socket, so foreground messages are ignored.
 */

const PROJECT_NAME = 'gameplan'
const TOKEN_STORAGE_KEY = `firebase_token_${PROJECT_NAME}`
const SERVICE_WORKER_URL = '/assets/gameplan/frontend/firebase-messaging-sw.js'

type Boot = Window & { push_relay_enabled?: boolean; push_relay_server_url?: string }
const boot = window as Boot

type RelayConfig = {
  config: {
    projectId: string
    appId: string
    apiKey: string
    authDomain: string
    messagingSenderId: string
  }
  vapid_public_key: string
}

/** The site can push (relay on) — the switch the settings page shows Push behind. */
export const pushRelayEnabled = Boolean(boot.push_relay_enabled)

/** This browser can do push at all (not, for example, an iOS Safari tab). */
export function isPushSupportedByBrowser() {
  return 'serviceWorker' in navigator && 'Notification' in window && 'PushManager' in window
}

/** Whether THIS device is registered; the stored token is the source of truth. */
export function isPushEnabledOnDevice() {
  return readStoredToken() !== null
}

/**
 * Turn push on for this device: permission, token, tell the server. Returns false — with
 * a toast saying why — when the browser refuses or the relay is not reachable.
 */
export async function enablePush(): Promise<boolean> {
  if (!pushRelayEnabled || !isPushSupportedByBrowser()) {
    toast.error('Push notifications are not available in this browser')
    return false
  }
  try {
    if (Notification.permission === 'denied') {
      toast.error('Notifications are blocked for this site in your browser settings')
      return false
    }
    if ((await Notification.requestPermission()) !== 'granted') {
      toast.error('Notifications were not allowed')
      return false
    }
    const token = await mintToken()
    await callSubscription('subscribe', token)
    storeToken(token)
    return true
  } catch (error) {
    captureError(error, { action: 'enable-push' })
    toast.error('Could not turn on push notifications')
    return false
  }
}

/** Turn push off for this device: forget the address on both sides. */
export async function disablePush(): Promise<void> {
  const token = readStoredToken()
  if (!token) return
  clearStoredToken()
  try {
    await callSubscription('unsubscribe', token)
    const { deleteToken } = await import('firebase/messaging')
    await deleteToken((await messaging()).messaging)
  } catch (error) {
    captureError(error, { action: 'disable-push' })
  }
}

/**
 * On app start, for a device that has push on: tokens rotate, so re-mint and re-register
 * if it changed. Quiet — nothing to say to the user either way.
 */
export async function refreshPushRegistration(): Promise<void> {
  const stored = readStoredToken()
  if (!stored || !pushRelayEnabled || !isPushSupportedByBrowser()) return
  if (Notification.permission !== 'granted') {
    clearStoredToken()
    return
  }
  try {
    const token = await mintToken()
    if (token !== stored) {
      await callSubscription('subscribe', token)
      storeToken(token)
    }
  } catch (error) {
    captureError(error, { action: 'refresh-push' })
  }
}

// ── the pieces ──────────────────────────────────────────────────────────────

/** The Firebase settings for this relay's project, fetched from the relay itself. */
async function relayConfig(): Promise<RelayConfig> {
  const base = boot.push_relay_server_url
  if (!base) throw new Error('push_relay_server_url is not set')
  const response = await fetch(
    `${base}/api/method/notification_relay.api.get_config?project_name=${PROJECT_NAME}`,
  )
  if (!response.ok) throw new Error(`Relay config failed (${response.status})`)
  return response.json()
}

async function messaging() {
  const [{ initializeApp, getApps }, { getMessaging, isSupported }, relay] = await Promise.all([
    import('firebase/app'),
    import('firebase/messaging'),
    relayConfig(),
  ])
  if (!(await isSupported())) throw new Error('Push is not supported on this device')
  // initializeApp twice with the same name throws — reuse the app across calls.
  const app = getApps()[0] ?? initializeApp(relay.config)
  return { messaging: getMessaging(app), vapidKey: relay.vapid_public_key }
}

async function mintToken(): Promise<string> {
  const registration = await navigator.serviceWorker.register(SERVICE_WORKER_URL)
  const { getToken } = await import('firebase/messaging')
  const { messaging: instance, vapidKey } = await messaging()
  const token = await getToken(instance, { vapidKey, serviceWorkerRegistration: registration })
  if (!token) throw new Error('No push token was issued')
  return token
}

async function callSubscription(method: 'subscribe' | 'unsubscribe', token: string) {
  const params = new URLSearchParams({ fcm_token: token, project_name: PROJECT_NAME })
  const response = await fetch(`/api/method/frappe.push_notification.${method}?${params}`, {
    headers: {
      'X-Frappe-CSRF-Token': (window as Window & { csrf_token?: string }).csrf_token ?? '',
    },
  })
  if (!response.ok) throw new Error(`Push ${method} failed (${response.status})`)
  const body = await response.json()
  if (body?.message?.success === false)
    throw new Error(body.message.message || `Push ${method} refused`)
}

function readStoredToken() {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY)
  } catch {
    return null
  }
}

function storeToken(token: string) {
  try {
    localStorage.setItem(TOKEN_STORAGE_KEY, token)
  } catch {
    /* private mode: the device simply is not remembered as registered */
  }
}

function clearStoredToken() {
  try {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
  } catch {
    /* nothing to clear */
  }
}
