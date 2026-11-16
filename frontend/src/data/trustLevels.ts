// Site-wide trust levels that mirror Discourse (decisions D103 to D132). The server owns every
// rule; this file names the shapes it returns and turns requirements into short sentences.

export const LEVEL_NAMES = ['New', 'Basic', 'Member', 'Regular', 'Leader'] as const

export type LevelNumber = 0 | 1 | 2 | 3 | 4

export const levelDescriptions: Record<LevelNumber, string> = {
  0: 'Posts wait for approval where a Community requires it. New-user limits apply.',
  1: 'New-user limits no longer apply. The site content caps do.',
  2: 'Can post twice as often.',
  3: 'Posts skip the content caps. Kept while the member stays active.',
  4: 'Set by a global admin. Same as Regular, and never rechecked.',
}

export type Requirement = { key: string; required: number; actual: number; met: boolean }

export type LevelProgress = {
  level: LevelNumber
  locked: number
  grace_until?: string | null
  target: LevelNumber | null
  window: number
  restriction_days: number
  requirements: Requirement[]
}

export type MemberLevel = {
  user: string
  full_name?: string
  level: LevelNumber
  locked: number
  grace_until?: string | null
  pending: number
}

export const SETTING_GROUPS: { title: string; fields: [string, string][] }[] = [
  {
    title: 'Basic',
    fields: [
      ['basic_entered', 'Discussions entered'],
      ['basic_days', 'Days visited'],
      ['basic_accepted', 'Accepted posts'],
    ],
  },
  {
    title: 'Member',
    fields: [
      ['member_days', 'Days visited'],
      ['member_given', 'Reactions given'],
      ['member_received', 'Reactions received'],
      ['member_replied', 'Discussions replied to'],
      ['member_entered', 'Discussions entered'],
    ],
  },
  {
    title: 'Regular',
    fields: [
      ['regular_window', 'Window, days'],
      ['regular_days', 'Days visited'],
      ['regular_replied', 'Discussions replied to'],
      ['regular_entered_percent', 'New discussions entered, %'],
      ['regular_entered_max', 'Discussions entered, at most'],
      ['regular_given', 'Reactions given'],
      ['regular_received', 'Reactions received'],
      ['regular_received_users', 'From this many people'],
      ['regular_max_removed', 'Posts removed, at most'],
      ['regular_restriction_days', 'Days without a ban or silence'],
      ['regular_grace_days', 'Grace period, days'],
    ],
  },
]

export type TrustSettings = { enabled: number; ranges: Record<string, [number, number]> } & Record<
  string,
  number
>

function plural(count: number, word: string) {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}

/** One sentence per requirement, for staff and for the member. */
export function requirementLabel(step: Requirement, progress: LevelProgress) {
  const { actual, required } = step
  switch (step.key) {
    case 'entered':
      return `${actual} of ${plural(required, 'discussion')} entered`
    case 'days':
      return `Visited on ${actual} of ${plural(required, 'day')}`
    case 'accepted':
      return `${actual} of ${plural(required, 'accepted post')}`
    case 'given':
      return `${actual} of ${plural(required, 'reaction')} given`
    case 'received':
      return `${actual} of ${plural(required, 'reaction')} received`
    case 'received_users':
      return `Reactions from ${actual} of ${required} ${required === 1 ? 'person' : 'people'}`
    case 'replied':
      return `Replied in ${actual} of ${plural(required, 'discussion')}`
    case 'removed':
      return `${plural(actual, 'post')} removed by moderators, at most ${required}`
    case 'restrictions':
      return step.met
        ? `No ban, suspension or silence in the last ${plural(progress.restriction_days, 'day')}`
        : `A ban, suspension or silence in the last ${plural(progress.restriction_days, 'day')}`
    default:
      return step.key
  }
}

/** The heading over the requirement list. */
export function progressHeading(progress: LevelProgress) {
  if (progress.target === null) return 'This is the highest level.'
  const name = LEVEL_NAMES[progress.target]
  if (progress.level === 3) return `To stay a Regular, over the last ${progress.window} days`
  if (progress.target === 3) return `For ${name}, over the last ${progress.window} days`
  return `For ${name}`
}
