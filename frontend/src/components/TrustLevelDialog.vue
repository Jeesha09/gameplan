<template>
  <Dialog v-model:open="open" :title="title" :dismissible="!saving">
    <p class="mb-4 text-base text-ink-gray-6">
      {{ member.full_name || member.user }} · currently {{ LEVEL_NAMES[member.level] }}
      <span v-if="member.locked"> (locked)</span>
    </p>
    <template v-if="mode === 'level'">
      <Select v-model="level" label="Level" :options="levelOptions" :disabled="saving" />
      <p class="mt-2 text-p-sm text-ink-gray-6">
        {{ levelDescriptions[Number(level) as LevelNumber] }}
      </p>
      <p v-if="!member.locked" class="mt-2 text-p-sm text-ink-gray-6">
        The rules can still change this level later. Lock it to keep it as set.
      </p>
    </template>
    <p v-else class="text-p-sm text-ink-gray-6">
      {{
        member.locked
          ? 'Unlocking lets the rules change this level again.'
          : 'Locking keeps this level as it is. The rules stop changing it until it is unlocked.'
      }}
    </p>
    <Textarea
      v-model="reason"
      class="mt-4"
      label="Reason (seen by global admins only)"
      :maxlength="500"
      :disabled="saving"
      required
    />
    <ErrorMessage
      v-if="error"
      class="mt-3"
      :message="extractServerMessage(error) || 'Could not change the level'"
    />
    <template #actions>
      <Button
        variant="solid"
        :disabled="!reason.trim() || (mode === 'level' && Number(level) === member.level)"
        :loading="saving"
        @click="save"
        >{{ confirmLabel }}</Button
      >
    </template>
  </Dialog>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button, Dialog, ErrorMessage, Select, Textarea, call, toast } from 'frappe-ui'
import { extractServerMessage } from '@/utils'
import {
  LEVEL_NAMES,
  levelDescriptions,
  type LevelNumber,
  type MemberLevel,
} from '@/data/trustLevels'

const props = defineProps<{ member: MemberLevel; mode: 'level' | 'lock' }>()
const emit = defineEmits<{ saved: [] }>()
const open = defineModel<boolean>('open', { default: false })
const level = ref(String(props.member.level))
const reason = ref('')
const saving = ref(false)
const error = ref<unknown>(null)
const levelOptions = LEVEL_NAMES.map((name, index) => ({
  label: `${index} ${name}`,
  value: String(index),
}))
const title = computed(() =>
  props.mode === 'level' ? 'Change level' : props.member.locked ? 'Unlock level' : 'Lock level',
)
const confirmLabel = computed(() =>
  props.mode === 'level' ? 'Change level' : props.member.locked ? 'Unlock' : 'Lock',
)

async function save() {
  saving.value = true
  error.value = null
  try {
    if (props.mode === 'level') {
      await call('gameplan.trust_levels.set_level', {
        user: props.member.user,
        level: Number(level.value),
        reason: reason.value,
      })
      toast.success(`Level changed to ${LEVEL_NAMES[Number(level.value)]}.`)
    } else {
      await call('gameplan.trust_levels.set_lock', {
        user: props.member.user,
        locked: props.member.locked ? 0 : 1,
        reason: reason.value,
      })
      toast.success(props.member.locked ? 'Level unlocked.' : 'Level locked.')
    }
    open.value = false
    emit('saved')
  } catch (e) {
    error.value = e
  } finally {
    saving.value = false
  }
}
</script>
