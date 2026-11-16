<template>
  <div class="flex items-center justify-between gap-3 pb-3">
    <TabButtons
      v-model="status"
      :options="
        ['Pending', 'Approved', 'Rejected', 'Withdrawn'].map((v) => ({ label: v, value: v }))
      "
    />
    <slot name="actions" />
  </div>
  <ErrorMessage
    v-if="error"
    class="py-3"
    :message="extractServerMessage(error) || 'Could not load submissions'"
  />
  <p v-if="loading" role="status" class="py-6 text-base text-ink-gray-5">Loading submissions…</p>
  <div v-else-if="items.length" class="border-t border-outline-gray-1">
    <ModerationRow v-for="item in items" :key="item.name">
      <template #lead
        ><Avatar
          :image="useUser(item.owner).user_image"
          :label="useUser(item.owner).full_name"
          size="md"
      /></template>
      <template #title>
        {{
          item.title ||
          (item.discussion_title
            ? `Reply in “${item.discussion_title}”`
            : `Reply to #${item.discussion}`)
        }}
      </template>
      <template v-if="item.excerpt" #detail>{{ item.excerpt }}</template>
      <template #meta>
        {{ useUser(item.owner).full_name }} ·
        <span :title="dayjsLocal(item.creation).format('D MMM YYYY [at] h:mm A')">{{
          dayjsLocal(item.creation).fromNow()
        }}</span>
      </template>
      <template #status>
        <Badge v-if="item.edit_name" label="Edit" />
        <Badge v-else :label="item.discussion ? 'Reply' : 'Discussion'" />
      </template>
      <template #actions>
        <Button variant="subtle" @click="inspect(item.name)">{{
          communityId && status === 'Pending' ? 'Review' : 'View'
        }}</Button>
      </template>
    </ModerationRow>
  </div>
  <ModerationEmpty
    v-else-if="!error"
    icon="lucide-check-check"
    :title="`No ${status.toLowerCase()} submissions`"
    :description="
      communityId && status === 'Pending'
        ? 'Posts from new members appear here before they are published.'
        : undefined
    "
  />
  <ModerationPager
    :previous="start > 0"
    :next="hasMore"
    @previous="changePage(-40)"
    @next="changePage(40)"
  />
  <ModerationDialog
    v-model:open="open"
    title="Review submission"
    :busy="saving"
    :content-key="active"
  >
    <template v-if="details">
      <p class="text-base-medium">
        {{ details.title || `Reply to discussion #${details.discussion}` }}
      </p>
      <p class="mt-2 text-base text-ink-gray-5">
        {{ details.status }} · {{ useUser(details.owner).full_name }}
      </p>
      <CommentEditor :key="details.name" :value="details.content" :editable="false" />
    </template>
    <template v-if="details" #sidebar>
      <div class="space-y-4 text-ink-gray-9">
        <p class="text-base-medium">{{ useUser(details.owner).full_name }}</p>
        <p class="text-base text-ink-gray-6">
          {{ details.status }} · {{ dayjsLocal(details.creation).format('D MMM YYYY') }}
        </p>
        <template v-if="details.status === 'Pending' && communityId">
          <Select
            v-model="decision"
            class="mt-4"
            label="Decision"
            :disabled="saving"
            :options="['Approve', 'Reject']"
          />
          <Textarea
            v-model="note"
            class="mt-3"
            label="Feedback visible to the author"
            :required="decision === 'Reject'"
            :maxlength="500"
            :disabled="saving"
          />
        </template>
        <p v-if="details.decision_note" class="mt-4 whitespace-pre-wrap text-base">
          {{ details.decision_note }}
        </p>
        <Button v-if="details.status === 'Approved'" class="mt-4" :route="publishedRoute"
          >Open published post</Button
        >
      </div>
    </template>
    <ErrorMessage
      v-if="detailError"
      class="mt-3"
      :message="extractServerMessage(detailError) || 'Could not review this submission'"
    />
    <template #actions>
      <Button v-if="detailError" :disabled="saving" @click="inspect(active)"
        >Refresh submission</Button
      >
      <Button
        v-if="details?.status === 'Pending' && communityId"
        variant="solid"
        :loading="saving"
        :disabled="decision === 'Reject' && !note.trim()"
        @click="resolve(decision)"
        >{{ decision }}</Button
      >
      <Button
        v-if="details?.status === 'Pending' && !communityId"
        :loading="saving"
        @click="withdraw"
        >Withdraw submission</Button
      >
    </template>
  </ModerationDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  Avatar,
  Badge,
  Button,
  ErrorMessage,
  Select,
  TabButtons,
  Textarea,
  call,
  dayjsLocal,
  dialog,
} from 'frappe-ui'
import ModerationEmpty from './moderation/ModerationEmpty.vue'
import ModerationPager from './moderation/ModerationPager.vue'
import ModerationRow from './moderation/ModerationRow.vue'
import ModerationDialog from './ModerationDialog.vue'
import CommentEditor from '@/components/editor/CommentEditor.vue'
import { useUser } from '@/data/users'
import { reloadDiscussionLists } from '@/data/discussions'
import { extractServerMessage } from '@/utils'
const props = defineProps<{ communityId?: string }>()
type Submission = {
  name: string
  edit_name?: string
  title?: string
  discussion?: string
  discussion_title?: string
  excerpt?: string
  owner: string
  creation: string
  status: string
  modified: string
  content: string
  decision_note?: string
  published_doctype?: string
  published_name?: string
  current_project: string
  current_community: string
}
const items = ref<Submission[]>([]),
  details = ref<Submission | null>(null)
const status = ref('Pending'),
  start = ref(0),
  hasMore = ref(false),
  loading = ref(false),
  open = ref(false),
  saving = ref(false)
const error = ref<unknown>(null),
  detailError = ref<unknown>(null)
const active = ref(''),
  decision = ref('Approve'),
  note = ref('')
let listRequest = 0,
  detailRequest = 0
const publishedRoute = computed(() => ({
  name: 'Discussion',
  params: {
    communityId: details.value?.current_community,
    spaceId: details.value?.current_project,
    postId: details.value?.discussion || details.value?.published_name,
  },
  query: details.value?.discussion ? { comment: details.value.published_name } : {},
}))
async function load() {
  const current = ++listRequest
  items.value = []
  error.value = null
  loading.value = true
  try {
    const result = await call<{ items: Submission[]; has_more: boolean }>(
      'gameplan.approvals.queue',
      { community: props.communityId || '', status: status.value, start: start.value },
    )
    if (current === listRequest) {
      items.value = result.items
      hasMore.value = result.has_more
    }
  } catch (e) {
    if (current === listRequest) error.value = e
  } finally {
    if (current === listRequest) loading.value = false
  }
}
watch(
  [() => props.communityId, status],
  () => {
    start.value = 0
    open.value = false
    detailRequest++
    load()
  },
  { immediate: true },
)
function changePage(delta: number) {
  start.value += delta
  load()
}
async function inspect(name: string) {
  const current = ++detailRequest
  active.value = name
  details.value = null
  detailError.value = null
  decision.value = 'Approve'
  note.value = ''
  open.value = true
  try {
    const result = await call<Submission>('gameplan.approvals.detail', { name })
    if (current === detailRequest) details.value = result
  } catch (e) {
    if (current === detailRequest) detailError.value = e
  }
}
async function resolve(action: string) {
  if (!details.value || saving.value) return
  saving.value = true
  detailError.value = null
  try {
    await call('gameplan.approvals.decide', {
      name: details.value.name,
      decision: action,
      expected_modified: details.value.modified,
      note: note.value,
    })
    open.value = false
    reloadDiscussionLists()
    await load()
  } catch (e) {
    detailError.value = e
  } finally {
    saving.value = false
  }
}
function withdraw() {
  dialog.confirm({
    title: 'Withdraw submission',
    message: 'This submission will leave the approval queue. Its history stays available.',
    confirmLabel: 'Withdraw',
    onConfirm: () => resolve('Withdraw'),
  })
}
</script>
