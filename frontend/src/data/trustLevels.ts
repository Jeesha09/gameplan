// Site-wide trust levels that mirror Discourse (decisions D103 to D132). The server owns every
// rule; this file names the shapes it returns and turns requirements into short sentences.

export const LEVEL_NAMES = ['New', 'Basic', 'Contributor', 'Regular', 'Leader'] as const

export type LevelNumber = 0 | 1 | 2 | 3 | 4

export const levelDescriptions: Record<LevelNumber, string> = {
  0: 'Posts wait for approval where a Community requires it. New-account limits apply on the first day, on replies in a row, and on links, media, files and mentions in each post.',
  1: 'The New limits end, apart from a higher limit on the first day. The site per-post limits apply.',
  2: 'Can post twice as often.',
  3: 'Posts skip the per-post limits. Kept while the member stays active.',
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

export type SettingSection = { title: string; description?: string; fields: [string, string][] }

export const SETTING_GROUPS: { title: string; sections: SettingSection[] }[] = [
  {
    title: 'New',
    sections: [
      {
        title: 'First day limits',
        description: 'In the 24 hours after the account is created. Polls count as replies',
        fields: [
          ['new_first_day_discussions', 'Discussions'],
          ['new_first_day_replies', 'Replies'],
        ],
      },
      {
        title: 'Replies in a row',
        description:
          "Replies in someone else's discussion before another person replies. Their own discussions have no limit",
        fields: [['new_replies_per_discussion', 'Replies']],
      },
      {
        title: 'Each post',
        description:
          '0 means none allowed. The site per-post limits also apply, and the lower number wins',
        fields: [
          ['new_max_links', 'Links'],
          ['new_max_media', 'Images and videos'],
          ['new_max_attachments', 'Files'],
          ['new_max_mentions', 'Mentions'],
        ],
      },
    ],
  },
  {
    title: 'Basic',
    sections: [
      {
        title: 'Visits',
        description: 'Counted since they joined',
        fields: [
          ['basic_days', 'Days visited'],
          ['basic_entered', 'Discussions opened'],
        ],
      },
      {
        title: 'Posting',
        description: 'Discussions and replies that were published and not removed',
        fields: [['basic_accepted', 'Posts published']],
      },
      {
        title: 'First day limits',
        description:
          'In the 24 hours after the account is created, counting what they posted while New. Cannot be lower than New',
        fields: [
          ['basic_first_day_discussions', 'Discussions'],
          ['basic_first_day_replies', 'Replies'],
        ],
      },
    ],
  },
  {
    title: 'Contributor',
    sections: [
      {
        title: 'Visits',
        description: 'Counted since they joined',
        fields: [
          ['contributor_days', 'Days visited'],
          ['contributor_entered', 'Discussions opened'],
        ],
      },
      {
        title: 'Taking part',
        description: 'Counted since they joined. Several replies in one discussion count once',
        fields: [
          ['contributor_replied', 'Discussions replied to'],
          ['contributor_given', 'Reactions given'],
          ['contributor_received', 'Reactions received'],
        ],
      },
    ],
  },
  {
    title: 'Regular',
    sections: [
      {
        title: 'Time frame',
        description:
          'Regular only counts recent activity, and members lose it if they stop meeting it',
        fields: [
          ['regular_window', 'Days to look back'],
          ['regular_grace_days', 'Grace period, days'],
        ],
      },
      {
        title: 'Visits',
        description:
          'A share of the discussions started in that time, with a cap so busy sites stay reachable',
        fields: [
          ['regular_days', 'Days visited'],
          ['regular_entered_percent', 'Discussions opened, %'],
          ['regular_entered_max', 'Never more than'],
        ],
      },
      {
        title: 'Taking part',
        description: 'Counted over the days above. Several replies in one discussion count once',
        fields: [
          ['regular_replied', 'Discussions replied to'],
          ['regular_given', 'Reactions given'],
          ['regular_received', 'Reactions received'],
          ['regular_received_users', 'From different people'],
        ],
      },
      {
        title: 'Good standing',
        description: 'Posts removed by moderators are counted over the days above',
        fields: [
          ['regular_max_removed', 'Posts removed, at most'],
          ['regular_restriction_days', 'Days with no restriction'],
        ],
      },
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
