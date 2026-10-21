import { resetData } from '../../support/seed'

describe('Archived space content', () => {
  let community: string
  let space: string
  let discussion: string

  beforeEach(() => {
    resetData('onboarded').then((ids) => {
      community = String(ids.community)
      space = String(ids.space)

      cy.request('POST', '/api/v2/document/GP%20Discussion', {
        title: 'Archived discussion',
        content: '<p>Existing discussion stays available.</p>',
        project: space,
      }).then(({ body }) => {
        discussion = String(body.data.name)
      })
      cy.request('POST', `/api/v2/document/GP%20Project/${space}/method/archive`)
    })
    cy.loginAs('member')
  })

  it('offers no way to comment on a discussion', () => {
    // Asserts the content rendered first, so an absent composer cannot be mistaken
    // for a page that never loaded.
    cy.visit(`/g/community/${community}/space/${space}/discussion/${discussion}`)
    cy.contains('Existing discussion stays available.').should('be.visible')
    cy.contains('Add a comment').should('not.exist')
  })
})
