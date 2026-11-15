import { dialog, toast } from 'frappe-ui'
import type { Router } from 'vue-router'
import { clearConversation, setBlocked, setMuted, type Conversation } from '@/data/messages'
import { useUser } from '@/data/users'

export function conversationActions(row: Conversation, router: Router) {
  return [
    {
      label: row.muted ? 'Unmute' : 'Mute',
      icon: row.muted ? 'lucide-bell' : 'lucide-bell-off',
      onClick: () => toggleMuted(row),
    },
    ...(row.is_group || row.people.length !== 1 ? [] : [blockAction(row.people[0])]),
    {
      label: 'Delete chat',
      icon: 'lucide-trash-2',
      theme: 'red' as const,
      onClick: () => confirmClear(row, router),
    },
  ]
}

export function blockAction(user: string) {
  const blocked = Boolean(useUser(user).blocked)
  return {
    label: blocked ? 'Unblock' : 'Block',
    icon: blocked ? 'lucide-circle-check' : 'lucide-ban',
    onClick: () => (blocked ? toggleBlocked(user, false) : confirmBlock(user)),
  }
}

function confirmBlock(user: string) {
  const name = useUser(user).full_name
  dialog.danger({
    title: `Block ${name}?`,
    message: `Neither of you will be able to message the other. ${name} won't be told, and group chats aren't affected. You can unblock them any time.`,
    confirmLabel: 'Block',
    onConfirm: async () => {
      await toggleBlocked(user, true)
    },
  })
}

export async function toggleBlocked(user: string, blocked: boolean) {
  try {
    await setBlocked(user, blocked)
    toast.success(blocked ? 'Blocked' : 'Unblocked')
    return true
  } catch {
    toast.error(blocked ? 'Could not block this person' : 'Could not unblock this person')
    return false
  }
}

async function toggleMuted(row: Conversation) {
  const muted = !row.muted
  row.muted = muted ? 1 : 0
  try {
    await setMuted(row.name, muted)
    toast.success(muted ? 'Conversation muted' : 'Conversation unmuted')
  } catch {
    row.muted = muted ? 0 : 1
    toast.error('Could not update this conversation')
  }
}

function confirmClear(row: Conversation, router: Router) {
  const name = row.people.map((user) => useUser(user).full_name).join(', ')
  dialog.danger({
    title: 'Delete chat',
    message: `This removes the chat and its messages from your list. ${name} still ${row.people.length > 1 ? 'keep' : 'keeps'} their copy. New messages will bring the chat back.`,
    confirmLabel: 'Delete',
    onConfirm: async () => {
      await clearConversation(row.name)
      const current = router.currentRoute.value
      if (current.name === 'Conversation' && current.params.conversationId === row.name) {
        router.replace({ name: 'Messages' })
      }
    },
  })
}
