import { reactive } from 'vue'

export interface SiteSettings {
  logo: string
  logo_dark: string
  favicon: string
  default_quick_reactions: string[]
  tags_enabled: boolean
  polls_enabled: boolean
  direct_messages_enabled: boolean
  search_enabled: boolean
  can_start_conversations: boolean
  can_invite_people: boolean
  min_title_length: number
  max_title_length: number
  min_post_length: number
  restrict_content_management: boolean
  /** The signed-in member's trust level, or -1 while levels are off or without one. */
  trust_level: number
}

export const siteSettings = reactive<SiteSettings>({
  logo: '',
  logo_dark: '',
  favicon: '',
  default_quick_reactions: [],
  tags_enabled: true,
  polls_enabled: true,
  direct_messages_enabled: true,
  search_enabled: true,
  can_start_conversations: true,
  can_invite_people: false,
  min_title_length: 0,
  max_title_length: 0,
  min_post_length: 0,
  restrict_content_management: false,
  trust_level: -1,
})

export function loadSiteSettings() {
  Object.assign(siteSettings, window.site_settings)
  applyFavicon()
}

export function applyFavicon() {
  if (!siteSettings.favicon) return
  document.querySelectorAll<HTMLLinkElement>('link[rel="icon"]').forEach((link) => {
    link.href = siteSettings.favicon
  })
}
