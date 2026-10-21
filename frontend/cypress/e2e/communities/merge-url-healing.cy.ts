import { resetData } from '../../support/seed'

type InsertedDoc = {
  name: string
  slug?: string
}

// The merge chain is the behaviour under test, so the extra communities are built
// inline: the seeded scenario only supplies the community, space and discussion this
// world starts from.
describe('Community merge URL healing', () => {
  let sourceCommunity: string
  let middleCommunity: string
  let finalCommunity: string
  let space: string
  let discussionId: string
  let discussionSlug: string

  beforeEach(() => {
    resetData('space_with_discussion')
      .then((ids) => {
        sourceCommunity = String(ids.community)
        space = String(ids.space)
        discussionId = String(ids.discussion)
        discussionSlug = String(ids.discussion_slug)

        return insertDoc<InsertedDoc>({ doctype: 'GP Team', title: 'Middle Community' })
      })
      .then((community) => {
        middleCommunity = community.name

        return insertDoc<InsertedDoc>({ doctype: 'GP Team', title: 'Final Community' })
      })
      .then((community) => {
        finalCommunity = community.name

        return mergeCommunity(sourceCommunity, middleCommunity)
      })
      .then(() => {
        return mergeCommunity(middleCommunity, finalCommunity)
      })

    cy.loginAs('admin')
  })

  it('heals stale discussion URLs from the content record', () => {
    assertHealsToCanonicalRoute(
      `/g/community/${sourceCommunity}/space/${space}/discussion/${discussionId}/${discussionSlug}`,
      `/g/community/${finalCommunity}/space/${space}/discussion/${discussionId}/${discussionSlug}`,
    )
    cy.contains('h1:visible', 'Welcome thread').should('exist')
  })
})

function insertDoc<T>(doc: Record<string, unknown>) {
  return cy
    .request('POST', '/api/method/frappe.client.insert', { doc })
    .its('body.message')
    .then((inserted) => inserted as T)
}

function mergeCommunity(source: string, target: string) {
  return cy.request('POST', `/api/v2/document/GP%20Team/${source}/method/merge_into_team`, {
    team: target,
  })
}

function assertHealsToCanonicalRoute(stalePath: string, canonicalPath: string) {
  cy.visit(stalePath)
  cy.location('pathname').should('eq', canonicalPath)
}
