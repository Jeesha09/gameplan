import { dialog, toast } from 'frappe-ui'
import type { Router } from 'vue-router'
import { clearConversation, setMuted, type Conversation } from '@/data/messages'
import { useUser } from '@/data/users'

export function conversationActions(row: Conversation, router: Router) {
  return [
    {
      label: row.muted ? 'Unmute' : 'Mute',
      icon: row.muted ? 'lucide-bell' : 'lucide-bell-off',
      onClick: () => toggleMuted(row),
    },
    {
      label: 'Delete chat',
      icon: 'lucide-trash-2',
      theme: 'red' as const,
      onClick: () => confirmClear(row, router),
    },
  ]
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
    message: `This removes the chat and its messages from your list. ${name} still keeps their copy. New messages will bring the chat back.`,
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
