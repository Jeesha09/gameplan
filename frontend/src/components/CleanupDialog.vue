<template>
  <Dialog v-model:open="open" title="Remove all posts" :dismissible="!saving">
    <p class="mb-4 text-base text-ink-gray-6">
      Removes {{ label }}'s discussions and replies
      {{ community ? 'in this Community' : 'in every Community' }} as spam and rejects their pending
      submissions. You can undo it from History.
    </p>
    <Textarea v-model="reason" label="Reason" :maxlength="500" :disabled="saving" required />
    <ErrorMessage
      v-if="error"
      class="mt-3"
      :message="extractServerMessage(error) || 'Could not start the cleanup'"
    />
    <template #actions>
      <Button variant="solid" :loading="saving" :disabled="!reason.trim()" @click="save"
        >Remove all posts</Button
      >
    </template>
  </Dialog>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { Button, Dialog, ErrorMessage, Textarea, toast } from 'frappe-ui'
import { extractServerMessage } from '@/utils'
import { startCleanup } from '@/data/restrictions'

const props = defineProps<{ user: string; label: string; community?: string }>()
const open = defineModel<boolean>('open')
const reason = ref('')
const saving = ref(false)
const error = ref<unknown>(null)

async function save() {
  saving.value = true
  error.value = null
  try {
    await startCleanup(props.user, reason.value, props.community)
    open.value = false
  } catch (e) {
    error.value = e
  } finally {
    saving.value = false
  }
}
</script>
