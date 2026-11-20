import type { Community } from '@/data/communities'
import { getCommunity } from '@/data/communities'
import type { Space } from '@/data/spaces'
import { siteSettings } from '@/data/siteSettings'
import { isMemberAccess, VISIBILITY_ANONYMOUS } from '@/utils/visibility'

type PermissionUser = {
  name?: string | null
  role?: string
  banned_communities?: string[]
}

export function isCommunityBanned(communityId: string | undefined, user: PermissionUser) {
  // An empty Community is a site silence, which bans participation everywhere.
  const banned = user.banned_communities
  return Boolean(
    communityId && (banned?.includes(communityId) || banned?.includes('')) && !isGlobalAdmin(user),
  )
}

export function canManageCommunity(community: Community | null | undefined, user: PermissionUser) {
  if (!community || !user.name) return false
  if (isGlobalAdmin(user)) return true
  if (isGuest(user)) return false
  return isCommunityAdmin(community, user.name)
}

export function getManageableCommunities(communities: Community[], user: PermissionUser) {
  if (isGlobalAdmin(user)) return communities
  return communities.filter((community) => canManageCommunity(community, user))
}

export function isCommunityAdmin(community: Community | null | undefined, user: string) {
  return Boolean(community?.members?.some((member) => member.user === user && member.is_admin))
}

export function isGlobalAdmin(user: PermissionUser) {
  return user.name === 'Administrator' || user.role === 'Gameplan Admin'
}

export function isGuest(user: PermissionUser) {
  return user.role === 'Gameplan Guest'
}

export function isAnonymousEligibleSpace(space: Space | null | undefined) {
  const community = space && getCommunity(space.team)
  return Boolean(
    space &&
    !space.archived_at &&
    space.visibility === VISIBILITY_ANONYMOUS &&
    community &&
    !community.archived_at &&
    community.visibility === VISIBILITY_ANONYMOUS,
  )
}

/** Moving existing private content into public view needs publication approval. */
export function canMoveContentToSpace(
  source: Space | null | undefined,
  target: Space,
  user: PermissionUser,
) {
  return (
    isGlobalAdmin(user) || isAnonymousEligibleSpace(source) || !isAnonymousEligibleSpace(target)
  )
}

/**
 * Mirror of backend `can_manage_space`: global admins can manage any space,
 * guests never manage one, private-space members can manage their own space,
 * and public spaces are managed by community admins. Derived from
 * already-fetched space/community membership, so it adds no network round-trip.
 *
 * The guest check comes before the membership check because a guest can hold a
 * member row on a private space they were granted.
 */
export function canManageSpace(space: Space | null | undefined, user: PermissionUser) {
  if (!space || !user.name) return false
  if (isGlobalAdmin(user)) return true
  if (isGuest(user) || isCommunityBanned(space.team, user)) return false
  if (isMemberAccess(space.visibility)) {
    return Boolean(space.members?.some((member) => member.user === user.name))
  }
  return isCommunityAdmin(getCommunity(space.team), user.name)
}

export function canModerateCommunity(
  community: Community | null | undefined,
  user: PermissionUser,
) {
  if (!community || !user.name || user.name === 'Guest' || isGuest(user)) return false
  return (
    isGlobalAdmin(user) ||
    Boolean(
      community.members?.some(
        (member) => member.user === user.name && (member.is_admin || member.is_moderator),
      ),
    )
  )
}

export function canModerateSpace(space: Space | null | undefined, user: PermissionUser) {
  if (!space || !user.name || user.name === 'Guest' || isGuest(user)) return false
  if (isGlobalAdmin(user)) return true
  if (
    isMemberAccess(space.visibility) &&
    !space.members?.some((member) => member.user === user.name)
  )
    return false
  return canModerateCommunity(getCommunity(space.team), user)
}

/** Guests can never invite; otherwise invite rights follow space management. */
export function canInviteGuests(space: Space | null | undefined, user: PermissionUser) {
  if (isCommunityBanned(space?.team, user)) return false
  if (isGuest(user)) return false
  return canManageSpace(space, user)
}

type ContentDoc = { owner?: string | null } | null | undefined

/**
 * Mirror of backend `can_delete_content` (gameplan/permissions.py): global admins
 * always; the content owner (members and guests alike may delete what they
 * authored); guests have no further delete rights; otherwise a community admin of
 * the content's space's community. Gameplan is permissive — members create and edit
 * freely (edits are transparent via revisions) — so DELETE-others is the one content
 * action that stays gated.
 *
 * `space` is the content's space (GP Project); pass null/undefined for personal
 * content with no space, where only the owner or a global admin can delete.
 */
export function canDeleteContent(
  content: ContentDoc,
  space: Space | null | undefined,
  user: PermissionUser,
) {
  if (isCommunityBanned(space?.team, user)) return false
  if (!content || !user.name) return false
  if (isGlobalAdmin(user)) return true
  if (content.owner === user.name) return true
  if (isGuest(user)) return false
  if (!space) return false
  return isCommunityAdmin(getCommunity(space.team), user.name)
}

/**
 * Mirror of backend `can_edit_content` (gameplan/permissions.py): global admins
 * always; a guest only on content they authored (guests are participants but may
 * edit just their own posts/comments); any member on content inside a space
 * (Gameplan is community-driven, so space content is member-editable and edits
 * are transparent via revisions); personal content with no space only by its
 * owner. Callers render this only for content the user can already view, which
 * is the backend's view-gate precondition.
 *
 * `space` is the content's space (GP Project); pass null/undefined for personal
 * content with no space.
 */
export function canEditContent(
  content: ContentDoc,
  space: Space | null | undefined,
  user: PermissionUser,
) {
  if (isCommunityBanned(space?.team, user)) return false
  if (!content || !user.name) return false
  if (isGlobalAdmin(user)) return true
  if (isGuest(user)) return content.owner === user.name
  if (space) return true
  return content.owner === user.name
}

export type PostAction = 'edit' | 'retitle' | 'close' | 'pin'

const REGULAR = 3
const LEADER = 4

/**
 * What the signed-in member may do to a discussion, reply or poll. Mirror of backend
 * `post_actions` (gameplan/permissions.py, D136). With forum mode off, everyone who may edit
 * content in a Space may also retitle, move, close and pin it, except guests, who never move
 * or pin. With it on, authors edit and close their own posts, Regulars retitle and move, and
 * Leaders, Community staff and global admins do everything. `retitle` covers moving.
 */
export function postActions(
  content: ContentDoc,
  space: Space | null | undefined,
  user: PermissionUser,
): PostAction[] {
  if (!content || !user.name || isCommunityBanned(space?.team, user)) return []
  if (!siteSettings.restrict_content_management || !space) {
    if (!canEditContent(content, space, user)) return []
    return isGuest(user) ? ['edit', 'close'] : ['edit', 'retitle', 'close', 'pin']
  }
  if (managesPosts(space, user)) return ['edit', 'retitle', 'close', 'pin']
  if (content.owner === user.name)
    return isGuest(user) ? ['edit', 'close'] : ['edit', 'retitle', 'close']
  if (!isGuest(user) && siteSettings.trust_level >= REGULAR) return ['retitle']
  return []
}

/** In forum mode, Leaders, Community staff and global admins manage everyone's posts. */
export function managesPosts(space: Space | null | undefined, user: PermissionUser) {
  if (!user.name || isGuest(user)) return false
  return isGlobalAdmin(user) || canModerateSpace(space, user) || siteSettings.trust_level >= LEADER
}

/** Forum mode lets the people who manage posts reply in a closed discussion. */
export function canReplyWhenClosed(space: Space | null | undefined, user: PermissionUser) {
  return siteSettings.restrict_content_management && managesPosts(space, user)
}

export function canHighlightComment(discussion: ContentDoc, user: PermissionUser) {
  return Boolean(discussion && user.name && discussion.owner === user.name)
}
