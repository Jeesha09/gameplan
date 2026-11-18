// Badges that mirror Discourse (prd/badges.md). The server owns every rule; this file names the
// shapes it returns and the symbol each badge family is drawn with.

export type BadgeTier = 'Bronze' | 'Silver' | 'Gold'
export type BadgeGroup = 'Getting Started' | 'Community' | 'Posting'
export const BADGE_GROUPS: BadgeGroup[] = ['Getting Started', 'Community', 'Posting']

export type Badge = {
  name: string
  title: string
  description: string
  badge_group: BadgeGroup
  family: string
  tier: BadgeTier
}

export type ListedBadge = Badge & { holders: number; held: 0 | 1 }

export type HeldBadge = Badge & { count: number; granted_at: string; is_favorite: 0 | 1 }

export type BadgeHolder = {
  name: string
  user: string
  granted_at: string
  post?: { doctype: string; name: string; discussion: string; space: string; title: string }
}

/** The first favourite, as the user directory carries it for the hover card. */
export type FavoriteBadge = Pick<Badge, 'name' | 'title' | 'description' | 'family' | 'tier'>

export const MAX_FAVORITES = 3

/** From the boot data: turning badges on or off shows up after a reload. */
export function badgesEnabled() {
  return Boolean(window.badges_enabled)
}

/**
 * One symbol per family, drawn on a 24px grid with a 1.5px round stroke. The tiers of a
 * family share it and differ by medallion colour. Constant markup, never user input.
 */
export const BADGE_SYMBOLS: Record<string, string> = {
  autobiographer:
    '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8.5" cy="10.5" r="2"/><path d="M5.5 16c.6-1.4 1.7-2.25 3-2.25s2.4.85 3 2.25"/><path d="M14.5 10h3.5M14.5 13.5h3.5"/>',
  'first-like':
    '<path d="M12 19.5C7 16 3.5 12.8 3.5 9.25a4.25 4.25 0 0 1 8.5-.5 4.25 4.25 0 0 1 8.5.5c0 3.55-3.5 6.75-8.5 10.25z"/>',
  'first-mention':
    '<circle cx="12" cy="12" r="3.5"/><path d="M15.5 8.5v4.75a2.25 2.25 0 0 0 4.5 0V12a8 8 0 1 0-3.2 6.4"/>',
  reader:
    '<path d="M12 7c-1.8-1.3-4.3-2-8-2v12.5c3.7 0 6.2.7 8 2 1.8-1.3 4.3-2 8-2V5c-3.7 0-6.2.7-8 2z"/><path d="M12 7v12.5"/>',
  welcome:
    '<path d="M8 13V8a1.5 1.5 0 0 1 3 0v4M11 11.5V6a1.5 1.5 0 0 1 3 0v5.5M14 11.5V7.5a1.5 1.5 0 0 1 3 0V15a6 6 0 0 1-6 6h-.5a5.5 5.5 0 0 1-4.5-2.35L3.6 15.2a1.5 1.5 0 0 1 2.4-1.8L8 15.5"/><path d="M19.5 4.5c1 .8 1.5 1.9 1.5 3M3.5 7.5c0-1.5.6-2.7 1.7-3.5"/>',
  appreciated:
    '<path d="M12 3.5l2.6 5.3 5.9.85-4.25 4.15 1 5.85L12 16.9l-5.25 2.75 1-5.85L3.5 9.65l5.9-.85z"/>',
  'thank-you':
    '<path d="M12 10.5c-2.4-1.5-4-2.9-4-4.6a2 2 0 0 1 4-.4 2 2 0 0 1 4 .4c0 1.7-1.6 3.1-4 4.6z"/><path d="M3 14.5h2.5l3.5 1.5h3.5a1.5 1.5 0 0 1 0 3H9"/><path d="M13.5 18.5l4.6-2.2a1.5 1.5 0 0 1 1.55 2.55L14 21.5H7l-4-1.5"/>',
  enthusiast:
    '<rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M3.5 9.5h17M8 3v4M16 3v4"/><path d="M9 15l2 2 4-4"/>',
  anniversary:
    '<rect x="4" y="11" width="16" height="9.5" rx="2"/><path d="M4 14.75c1.33 0 1.87-1.25 2.67-1.25s1.33 1.25 2.66 1.25 1.87-1.25 2.67-1.25 1.33 1.25 2.67 1.25 1.86-1.25 2.66-1.25 1.34 1.25 2.67 1.25"/><path d="M12 7.5V11"/><path d="M12 2.5c1 1.1 1.4 1.9 1.4 2.6a1.4 1.4 0 0 1-2.8 0c0-.7.4-1.5 1.4-2.6z"/>',
  helper:
    '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="3.5"/><path d="M14.5 9.5l3.5-3.5M9.5 9.5L6 6M9.5 14.5L6 18M14.5 14.5l3.5 3.5"/>',
  reply:
    '<path d="M6.5 4.5h11A2.5 2.5 0 0 1 20 7v7a2.5 2.5 0 0 1-2.5 2.5h-7L6.5 20v-3.5A2.5 2.5 0 0 1 4 14V7a2.5 2.5 0 0 1 2.5-2.5z"/><path d="M8 9h8M8 12h5"/>',
  topic:
    '<path d="M5.5 9h9a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-5L6 20.5V18h-.5a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2z"/><path d="M8 9V6.5a2 2 0 0 1 2-2h8.5a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>',
}
