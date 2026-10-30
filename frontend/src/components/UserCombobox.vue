<template>
  <Combobox
    v-bind="$attrs"
    v-model:query="query"
    :options="options"
    :model-value="modelValue"
    :filterable="false"
    :loading="loading && !options.length"
    @update:model-value="emit('update:modelValue', $event)"
    @update:open="onOpen"
  >
    <template v-for="(_, name) in $slots" #[name]="slotProps">
      <slot :name="name" v-bind="slotProps ?? {}" />
    </template>
  </Combobox>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Combobox } from 'frappe-ui'
import { useUser, useUserSearch, type UserInfo, type UserSearchParams } from '@/data/users'

defineOptions({ inheritAttrs: false })

const props = defineProps<{
  modelValue?: string | null
  params?: UserSearchParams
  extraOptions?: { label: string; value: string }[]
  filter?: (user: UserInfo) => boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [value: string | null] }>()

const query = ref('')
const open = ref(false)

const { results, loading } = useUserSearch(() =>
  open.value ? { limit: props.filter ? 100 : 20, ...props.params, query: query.value } : null,
)

const options = computed(() => {
  const list = [
    ...(props.extraOptions ?? []),
    ...results.value
      .filter((user) => !props.filter || props.filter(user))
      .map((user) => ({ label: user.full_name, value: user.name })),
  ]
  const selected = props.modelValue
  if (selected && !list.some((option) => option.value === selected)) {
    list.unshift({ label: useUser(selected).full_name, value: selected })
  }
  return list
})

function onOpen(value: boolean) {
  open.value = value
  if (value) query.value = ''
}
</script>
