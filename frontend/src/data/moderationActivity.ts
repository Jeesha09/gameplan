import { ref } from 'vue'
import { call } from 'frappe-ui'

export interface ModerationActivity {
  approvals: number
  reports: number
  removed: boolean
  bans: boolean
  history: boolean
}

export type SeenTab = 'removed' | 'bans' | 'history'

export const moderationAttention = ref(false)

let attentionRequest = 0

export async function reloadModerationAttention() {
  const current = ++attentionRequest
  try {
    const result = await call<{ attention: boolean }>('gameplan.moderation_activity.activity')
    if (current === attentionRequest) moderationAttention.value = result.attention
  } catch {
    if (current === attentionRequest) moderationAttention.value = false
  }
}

export function loadCommunityActivity(community: string) {
  return call<ModerationActivity>('gameplan.moderation_activity.activity', { community })
}

export function markModerationTabSeen(community: string, tab: SeenTab) {
  return call('gameplan.moderation_activity.mark_seen', { community, tab })
}
