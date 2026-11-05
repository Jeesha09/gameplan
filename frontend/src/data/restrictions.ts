import { call, dayjs, getConfig, toast } from 'frappe-ui'

export type RestrictionUser = {
  user: string
  full_name?: string
  user_image?: string
  reason?: string
  kind?: 'Suspend' | 'Silence'
  expires_at?: string | null
  modified?: string
}

// Elapsed-time presets shared by restrictions and slow mode, in seconds.
export const durationPresets = [
  { label: '1 hour', value: '3600' },
  { label: '1 day', value: '86400' },
  { label: '1 week', value: '604800' },
  { label: '30 days', value: '2592000' },
  { label: 'Custom date and time', value: 'custom' },
]

export async function startCleanup(user: string, reason: string, community = '') {
  await call('gameplan.author_cleanup.start', { user, reason, community })
  toast.success('Cleanup started. The result appears in History.')
}

export function expiryLabel(value?: string | null) {
  if (!value) return 'Until manually lifted'
  const date = dayjs(value).tz(
    getConfig('localTimezone') || Intl.DateTimeFormat().resolvedOptions().timeZone,
  )
  return `${date.format('D MMM YYYY, h:mm A z')} (${date.fromNow()})`
}

export function restrictionTransition(item: {
  action: string
  expires_at?: string
  previous_expires_at?: string
}) {
  const date = (value?: string) =>
    value
      ? dayjs(value)
          .tz(getConfig('localTimezone') || Intl.DateTimeFormat().resolvedOptions().timeZone)
          .format('D MMM YYYY, h:mm A z')
      : 'Indefinite'
  if (item.action === 'Restriction Expired') return `Expired at ${date(item.expires_at)}`
  if (['Unban', 'Lift Suspension', 'Lift Silence'].includes(item.action))
    return `${date(item.previous_expires_at)} → Lifted`
  if (['Ban', 'Suspend', 'Silence'].includes(item.action)) return `Expiry: ${date(item.expires_at)}`
  return `${date(item.previous_expires_at)} → ${date(item.expires_at)}`
}
