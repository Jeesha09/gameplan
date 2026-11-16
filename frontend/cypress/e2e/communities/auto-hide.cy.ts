import { resetData, type SeedIds } from '../../support/seed'

const thread = (ids: SeedIds) =>
  `/g/community/${ids.community}/space/${ids.space}/discussion/${ids.discussion}/${ids.discussion_slug}`

function reportAs(user: string, ids: SeedIds) {
  cy.switchUser(user)
  cy.request('POST', '/api/method/gameplan.reporting.submit', {
    doctype: 'GP Discussion',
    name: String(ids.discussion),
    reason: 'Spam',
  })
}

function approvalSettings(ids: SeedIds) {
  cy.visit(`/g/community/${ids.community}/moderation`)
  cy.contains('button', 'Approval settings').click()
  // The switch stays disabled until the dialog has loaded its settings.
  cy.get('[data-testid="auto-hide-switch"]').should('be.visible').and('not.be.disabled')
}

describe('Weighted auto-hide', () => {
  it('hides a post when weighted reports reach the threshold, and Dismiss restores it', () => {
    resetData('space_with_discussion').then((ids) => {
      cy.request('POST', '/api/method/gameplan.trust_levels.save_settings', { enabled: 1 })
      cy.request('POST', '/api/method/gameplan.trust_levels.set_level', {
        user: 'member2@example.com',
        level: 3,
        reason: 'Long-time contributor',
      })

      // While auto-hide is off, the Reports page shows nothing about it.
      cy.visit(`/g/community/${ids.community}/moderation`)
      cy.contains('button', /^Reports$/).click()
      cy.contains('No pending reports').should('be.visible')
      cy.get('[data-testid="auto-hide-status"]').should('not.exist')

      approvalSettings(ids)
      cy.contains('label', 'Hide reported posts automatically').click()
      cy.get('[data-testid="auto-hide-threshold"]').should('have.value', '6')
      cy.contains('button', 'Save approval policy').click()
      cy.contains('Approval policy saved.').should('be.visible')

      // A Regular counts 3 and a global admin counts 3: together they reach 6.
      reportAs('secondMember', ids)
      reportAs('admin', ids)

      cy.visit(thread(ids))
      cy.contains('hidden after member reports and is waiting for review').should('be.visible')

      cy.visit(`/g/community/${ids.community}/moderation`)
      cy.contains('button', /^Reports$/).click()
      cy.get('[data-testid="auto-hide-status"]').should('contain.text', 'reach a weight of 6')
      cy.get('[data-testid="moderation-row"]')
        .first()
        .should('contain.text', 'Welcome thread')
        .and('contain.text', 'Hidden automatically')
        .contains('button', /^Review$/)
        .click()
      cy.get('[data-testid="report-weight"]')
        .should('contain.text', 'Report weight 6 of 6')
        .and('contain.text', 'hidden automatically')
      cy.get('[data-testid="review-content"]').should('contain.text', 'Welcome thread')
      cy.get('[role="dialog"]').should('contain.text', 'Restore the post and close the review')
      cy.get('[role="dialog"] textarea').type('Not spam')
      cy.get('[role="dialog"]').contains('button', 'Resolve review').click()
      cy.contains('No pending reports').should('be.visible')

      cy.visit(`/g/community/${ids.community}/moderation?tab=history`)
      cy.contains('Auto Hide').should('be.visible')
      cy.contains('by System').should('be.visible')

      cy.switchUser('member')
      // Opening the thread marks its notices read, so read them first.
      cy.visit('/g/notifications')
      cy.contains('was hidden after member reports').should('be.visible')
      cy.contains('made it visible again').should('be.visible')
      cy.visit(thread(ids))
      cy.contains('Seed content').should('be.visible')
    })
  })

  it('keeps the weights out of the review while auto-hide is off', () => {
    resetData('space_with_discussion').then((ids) => {
      cy.request('POST', '/api/method/gameplan.trust_levels.save_settings', { enabled: 1 })
      cy.request('POST', '/api/method/gameplan.auto_hide.save_settings', {
        community: ids.community,
        enabled: 1,
        threshold: 30,
      })
      reportAs('secondMember', ids)
      cy.switchUser('admin')
      cy.request('POST', '/api/method/gameplan.auto_hide.save_settings', {
        community: ids.community,
        enabled: 0,
        threshold: 30,
      })

      cy.visit(`/g/community/${ids.community}/moderation`)
      cy.contains('button', /^Reports$/).click()
      cy.get('[data-testid="moderation-row"]')
        .contains('button', /^Review$/)
        .click()
      cy.get('[aria-label="Reporter feedback"]').should('be.visible')
      cy.get('[data-testid="report-weight"]').should('not.exist')
      cy.get('[role="dialog"]').should('not.contain.text', 'auto-hide')
      cy.get('[data-testid="auto-hide-status"]').should('not.exist')
    })
  })
})
