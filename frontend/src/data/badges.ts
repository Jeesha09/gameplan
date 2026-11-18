// Badges that mirror Discourse (prd/badges.md). The server owns every rule; this file names the
// shapes it returns and the symbol each badge family is drawn with.
import type { InjectionKey, Ref } from 'vue'

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

/** A favourite, as the user directory carries it for the hover card. */
export type FavoriteBadge = Pick<Badge, 'name' | 'title' | 'description' | 'family' | 'tier'>

export const MAX_FAVORITES = 3

/** From the boot data: turning badges on or off shows up after a reload. */
export function badgesEnabled() {
  return Boolean(window.badges_enabled)
}

/** The profile that `ProfileBadgeRibbons` shows favourites for. Provided by `PersonProfile`. */
export const profileUserKey: InjectionKey<Readonly<Ref<string>>> = Symbol('profileUser')

/**
 * One symbol per family, drawn by hand as filled shapes on a 24px grid. The tiers of a family
 * share it and differ by colour. `s` is the symbol, `d` a detail cut back to the background,
 * and `sl` and `dl` are their stroked forms. Constant markup, never user input.
 */
export const BADGE_SYMBOLS: Record<string, string> = {
  autobiographer:
    '<path class="s" d="M12 2.9c4.3 0 7.3 4 7.3 9.2 0 5.3-3.1 9-7.4 9-4.2 0-7.2-3.8-7.2-9.1C4.7 6.8 7.8 2.9 12 2.9z"/><path class="d" d="M12.1 6.6c1.7 0 2.9 1.4 2.9 3.2 0 1.9-1.3 3.3-3 3.3s-2.9-1.5-2.9-3.3c0-1.8 1.3-3.2 3-3.2z"/><path class="d" d="M6.9 17.6c.9-2.3 2.8-3.5 5.2-3.5 2.3 0 4.2 1.1 5.1 3.4-1.3 1.6-3.1 2.5-5.2 2.5-2.1 0-3.9-.9-5.1-2.4z"/>',
  'first-like':
    '<path class="s" d="M12 20.4C6.4 16.7 3.5 13.5 3.7 9.7 3.9 6.6 6.2 4.6 8.8 4.7c1.5.1 2.6 1 3.2 2.3.7-1.4 1.9-2.4 3.6-2.4 2.8.1 4.8 2.3 4.6 5.3-.2 3.8-3.2 6.9-8.2 10.5z"/><path class="dl" stroke-width="1.4" d="M6.6 9.6c0-1.4.8-2.4 2.1-2.5"/>',
  'first-mention':
    '<path class="sl" stroke-width="2.3" d="M15.7 8.3v4.2c0 1.8.9 2.9 2.2 2.9 1.6 0 2.4-1.6 2.3-3.8C20 7.1 16.6 3.8 12 3.8 7.3 3.8 3.7 7.5 3.7 12.2s3.6 8.1 8.3 8.1c1.6 0 3-.4 4.3-1.1"/><path class="sl" stroke-width="2.3" d="M12 8.5c2 0 3.6 1.6 3.6 3.6 0 2.1-1.6 3.7-3.6 3.7s-3.5-1.6-3.5-3.6c0-2.1 1.5-3.7 3.5-3.7z"/>',
  reader:
    '<path class="s" d="M12 7.1C9.8 5.4 6.8 5 3.4 5.7v12.2c3.4-.6 6.4-.2 8.6 1.4z"/><path class="s" d="M12 7.1c2.3-1.8 5.4-2.2 8.7-1.5v12.1c-3.3-.6-6.4-.1-8.7 1.6z"/><path class="dl" stroke-width="1" d="M5.9 9c1.6-.2 2.9 0 4.1.6M5.9 11.7c1.6-.2 2.9 0 4.1.6M5.9 14.4c1.4-.2 2.4-.1 3.2.3M14 9.6c1.2-.7 2.6-.9 4.1-.7M14 12.3c1.2-.7 2.6-.9 4.1-.7"/><path class="d" d="M16.2 5.3v5l1-1 1 1V5.1z"/>',
  welcome:
    '<path class="sl" stroke-width="2.5" d="M8.5 12.6V6.9M10.7 11.6V4.7M12.9 11.6V5.4M15.1 12.6V7.6"/><path class="s" d="M7.1 11.3h9.2v3.6c0 3.2-2 5.5-4.7 5.5-2.2 0-3.8-1.2-4.8-3l-2.1-3.3c-.6-1 .6-2 1.5-1.3l.9.7z"/><path class="sl" stroke-width="1.4" d="M18.4 6.1c1.2 1 1.8 2.2 1.9 3.6M18 3.6c2.2 1 3.4 2.8 3.8 4.9"/>',
  appreciated:
    '<path class="s sw" stroke-width="1.6" d="M11.7 3.6l2.5 5.1 5.6.7-4.1 3.9 1.1 5.6-5-2.8-5 2.8 1-5.6-4.1-3.9 5.7-.8z"/><path class="s" d="M19.8 2.6c.2 1.4.6 1.8 2 2-1.4.2-1.8.6-2 2-.2-1.4-.6-1.8-2-2 1.4-.2 1.8-.6 2-2z"/>',
  'thank-you':
    '<path class="s" d="M12 12.6C9.2 10.8 7.8 9.2 7.9 7.2 8 5.7 9.2 4.7 10.4 4.8c.7 0 1.3.5 1.6 1.1.3-.7.9-1.1 1.7-1.1 1.3 0 2.4 1.1 2.3 2.6-.1 1.8-1.4 3.4-4 5.2z"/><path class="s" d="M3.4 15.3c2.2-.8 5-.9 7.4.1h2.8c1 0 1.3 1.4.2 1.7h-2.6 3c1 0 2.1-.5 3-1.2l1.8-1.5c.9-.7 2 .4 1.2 1.3l-2.8 2.9c-1.4 1.4-3.2 1.8-5.2 1.8H3.4z"/>',
  enthusiast:
    '<path class="s" d="M12 21c-3.8 0-6.4-2.6-6.4-6 0-3.6 2.8-5.4 3.8-8.4.4-1.2.3-2.4-.1-3.6 3.3 1 5.7 3.8 5.9 7 .7-.6 1.1-1.6 1.1-2.6 1.5 1.8 2.1 4.2 2.1 7.2 0 3.8-2.8 6.4-6.4 6.4z"/><path class="d" d="M12 19.3c-1.7 0-2.8-1.2-2.8-2.8 0-1.8 1.4-2.8 2.2-4.4 2 1 3.4 2.7 3.4 4.5 0 1.6-1.2 2.7-2.8 2.7z"/>',
  anniversary:
    '<path class="s" d="M5 13.4c0-.8.6-1.4 1.4-1.4h11.2c.8 0 1.4.6 1.4 1.4v6.3H5z"/><path class="dl" stroke-width="1.3" d="M5 14.6c1 1.2 2 1.2 2.6.2.6 1.2 2 1.3 2.6 0 .7 1.4 2.2 1.4 2.8 0 .6 1.2 2.1 1.3 2.8 0 .6 1 2 1 3.2-.2"/><path class="sl" stroke-width="1.6" d="M3.4 20.5h17.2"/><path class="s" d="M11.1 8.2h1.9v3.8h-1.9z"/><path class="s" d="M12 3.1c1.3 1.4 1.6 2.4 1.1 3.2-.3.5-1.9.5-2.2 0-.4-.8.1-1.8 1.1-3.2z"/>',
  helper:
    '<path class="sl" stroke-width="4.2" d="M12 4.9c4 0 7.1 3.1 7.1 7.1S16 19.1 12 19.1 4.9 16 4.9 12 8 4.9 12 4.9z"/><path class="dl" stroke-width="2.4" stroke-linecap="butt" d="M15.6 8.4l2.6-2.6M8.4 8.4L5.8 5.8M8.4 15.6l-2.6 2.6M15.6 15.6l2.6 2.6"/>',
  reply:
    '<path class="s" d="M4 11c0-4 3.4-6.6 8-6.6 4.7 0 8 2.6 8 6.4 0 3.8-3.4 6.4-8 6.4-1 0-1.9-.1-2.7-.4-1.3 1.6-3.1 2.6-5.1 2.8 1.2-1.2 1.8-2.4 1.9-4C4.8 14.4 4 12.8 4 11z"/><circle class="d" cx="8.6" cy="10.9" r="1.2"/><circle class="d" cx="12" cy="10.9" r="1.2"/><circle class="d" cx="15.4" cy="10.9" r="1.2"/>',
  topic:
    '<path class="s" fill-opacity=".55" d="M8.6 6.6v-.8c0-1.2.9-2 2-2h7.8c1.2 0 2 .8 2 2v4.8c0 1.2-.8 2-1.8 2.1V15l-1-.8"/><path class="s" d="M3.6 10.4c0-1.2.9-2 2.1-2h8.7c1.2 0 2.1.8 2.1 2v5.2c0 1.2-.9 2-2.1 2H9l-3.4 2.8v-2.8c-1.1-.1-2-.9-2-2z"/><path class="dl" stroke-width="1.2" d="M6.6 11.8h6.8M6.6 14.4H11"/>',
}
