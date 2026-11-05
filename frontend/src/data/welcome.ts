import { ref } from 'vue'
import { useCall } from 'frappe-ui'

const APP_NAME = 'gameplan'
const STATUS_KEY = `${APP_NAME}_onboarding_status`

export const showTour = ref(false)

const status = useCall<Record<string, unknown>>({
  url: '/api/v2/method/frappe.onboarding.get_onboarding_status',
  immediate: false,
})

const saveStatus = useCall<null, { steps: { name: string; completed: boolean }[]; appName: string }>({
  url: '/api/v2/method/frappe.onboarding.update_user_onboarding_status',
  method: 'POST',
  immediate: false,
})

let checked = false
let seen = true

export async function openTourIfNew() {
  if (checked) return
  checked = true
  await status.submit()
  seen = Boolean(status.data?.[STATUS_KEY])
  if (!seen) showTour.value = true
}

export function markTourSeen() {
  if (seen) return
  seen = true
  saveStatus.submit({ steps: [{ name: 'welcome', completed: true }], appName: APP_NAME })
}
