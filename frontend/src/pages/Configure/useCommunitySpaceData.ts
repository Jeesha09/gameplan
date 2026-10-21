import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useList } from 'frappe-ui'
import { spaces } from '@/data/spaces'
import type { GPGuestAccess } from '@/types/doctypes'

type GuestAccessRecord = Pick<GPGuestAccess, 'project'>

/**
 * Shared space-derived data for a community: the community's spaces plus the
 * per-space guest counts. Both the list (rows) and the fixed-header
 * controls need this; the underlying lists share cacheKeys so the data is
 * fetched once regardless of how many consumers mount.
 */
export function useCommunitySpaceData(communityId: MaybeRefOrGetter<string>) {
  const guestAccess = useList<GuestAccessRecord>({
    doctype: 'GP Guest Access',
    fields: ['project'],
    initialData: [],
    limit: 99999,
    cacheKey: 'space-guest-counts',
  })

  const communitySpaces = computed(() =>
    (spaces.data || []).filter((space) => space.team === toValue(communityId)),
  )

  const guestsCountBySpace = computed(() => {
    const counts: Record<string, number> = {}
    for (const access of guestAccess.data || []) {
      if (!access.project) continue
      counts[access.project] = (counts[access.project] || 0) + 1
    }
    return counts
  })

  const getGuestsCount = (spaceId: string) => guestsCountBySpace.value[spaceId] || 0

  const hasGuests = computed(() =>
    communitySpaces.value.some((space) => getGuestsCount(space.name) > 0),
  )

  return { communitySpaces, getGuestsCount, hasGuests }
}
