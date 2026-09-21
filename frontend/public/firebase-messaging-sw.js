// Push-only service worker: the small script the browser keeps around even when no
// Gameplan tab is open. Its whole job is to turn an arriving push into a notification
// and open the right page when it is clicked. Nothing is cached, nothing is intercepted.
//
// The Push Notification Relay sends the notification's title, body and link inside the
// message's `data` (Frappe's `send_notification_to_user` puts the link in `click_action`).
// The FCM `notification` shape is read too, in case a relay sends that instead.
//
// Registered by frontend/src/data/push.ts from /assets/gameplan/frontend/, so its scope
// is that folder — which is all a push-only worker needs.

self.addEventListener('push', (event) => {
  if (!event.data) return
  let payload = {}
  try {
    payload = event.data.json()
  } catch {
    payload = { data: { title: 'Gameplan', body: event.data.text() } }
  }
  const data = payload.data || {}
  const notification = payload.notification || {}
  const title = data.title || notification.title || 'Gameplan'
  const body = data.body || notification.body || ''
  const link = data.click_action || notification.click_action || '/g/notifications'
  const icon =
    data.notification_icon || notification.icon || '/assets/gameplan/frontend/favicon.png'

  event.waitUntil(
    // A tab that is open and visible already shows the in-app notification.
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      if (clients.some((client) => client.visibilityState === 'visible')) return
      return self.registration.showNotification(title, {
        body,
        icon,
        badge: icon,
        data: { link },
        // One notification per link: a second comment on the same post replaces the first.
        tag: link,
        renotify: true,
      })
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const link = (event.notification.data && event.notification.data.link) || '/g/notifications'
  const url = new URL(link, self.location.origin).href
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      const open = clients.find((client) => client.url.startsWith(self.location.origin))
      if (open) {
        // Reuse the tab that is already there; it navigates itself.
        return open.focus().then((client) => (client.navigate ? client.navigate(url) : client))
      }
      return self.clients.openWindow(url)
    }),
  )
})
