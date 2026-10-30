import { reactive, ref, watch } from 'vue'
import { call } from 'frappe-ui'
import type { GPUserProfile } from '@/types/doctypes'

interface Person extends Pick<GPUserProfile, 'name' | 'user' | 'bio' | 'modified'> {
  discussions_count: number
  comments_count: number
  reactions_given: number
  reactions_received: number
}

export type PeopleSortField =
  | 'full_name'
  | 'modified'
  | 'discussions_count'
  | 'comments_count'
  | 'reactions_received'
  | 'reactions_given'

type PeopleSortDirection = 'asc' | 'desc'

const sortChoices: { label: string; value: PeopleSortField }[] = [
  { label: 'Name', value: 'full_name' },
  { label: 'Last updated', value: 'modified' },
  { label: 'Posts', value: 'discussions_count' },
  { label: 'Replies', value: 'comments_count' },
  { label: 'Reactions received', value: 'reactions_received' },
  { label: 'Reactions given', value: 'reactions_given' },
]

export const peopleSortOptions = [
  { label: 'Sort by', value: '' as const, disabled: true },
  ...sortChoices,
]

export const peopleSearch = ref('')
export const peopleSortField = ref<PeopleSortField>('modified')
export const peopleSortDirection = ref<PeopleSortDirection>('desc')

export function sortPeopleBy(field: PeopleSortField) {
  if (peopleSortField.value === field) {
    peopleSortDirection.value = peopleSortDirection.value === 'asc' ? 'desc' : 'asc'
    return
  }
  peopleSortField.value = field
  peopleSortDirection.value = field === 'full_name' ? 'asc' : 'desc'
}

const PAGE_SIZE = 50
let request = 0

/** The People list, searched, sorted and paged on the server. The session user comes first. */
export const people = reactive({
  data: null as Person[] | null,
  error: null as unknown,
  loading: false,
  isFinished: false,
  hasNextPage: false,
  reload: () => loadPeople(true),
  next: () => loadPeople(false),
})

async function loadPeople(reset: boolean) {
  const current = ++request
  people.loading = true
  try {
    const rows = await call<Person[]>('gameplan.api.get_people', {
      query: peopleSearch.value,
      order_by: peopleSortField.value,
      descending: peopleSortDirection.value === 'desc',
      start: reset ? 0 : (people.data?.length ?? 0),
      limit: PAGE_SIZE,
    })
    if (current !== request) return
    people.data = reset ? rows : [...(people.data ?? []), ...rows]
    people.hasNextPage = rows.length === PAGE_SIZE
    people.error = null
  } catch (error) {
    if (current === request) people.error = error
  } finally {
    if (current === request) {
      people.loading = false
      people.isFinished = true
    }
  }
}

watch([peopleSearch, peopleSortField, peopleSortDirection], () => people.reload())
