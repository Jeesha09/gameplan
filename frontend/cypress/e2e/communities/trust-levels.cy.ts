import { resetData } from '../../support/seed'

function row(name: string) {
  return cy
    .get('[data-testid="trust-level-list"] [data-testid="moderation-row"]')
    .filter(`:contains("${name}")`)
}

function confirm(reason: string, button: string) {
  cy.get('[role="dialog"] textarea').type(reason)
  cy.get('[role="dialog"]').contains('button', button).click()
}

describe('Trust levels', () => {
  it('lets a global admin turn levels on, change and lock a level, and shows the member their level', () => {
    resetData('space_with_discussion').then((ids) => {
      cy.visit('/g/moderation?scope=site&tab=trust-levels')
      cy.contains('Trust levels are off').should('be.visible')

      cy.contains('button', 'Trust level settings').click()
      cy.get('[role="dialog"]').contains('Regular needs').should('be.visible')
      cy.contains('label', 'Use trust levels').click()
      cy.contains('button', 'Save trust levels').click()
      cy.contains('Trust levels saved.').should('be.visible')

      // No job worker runs here, so the first calculation has not reached anyone yet.
      cy.contains('[role="radio"]', 'Not worked out').click()
      row('Second Member').should('contain.text', 'Not worked out yet')
      cy.contains('[role="radio"]', 'All').click()

      row('Second Member').find('button[aria-label="More actions"]').click()
      cy.contains('[role="menuitem"]', 'Show requirements').click()
      cy.get('[data-testid="trust-requirements"]')
        .should('contain.text', 'For Basic')
        .and('contain.text', 'discussions entered')

      row('Second Member')
        .contains('button', /^\s*Change\s*$/)
        .click()
      cy.get('[role="dialog"]').contains('button', '0 New').click()
      cy.contains('[role="option"]', '3 Regular').click()
      confirm('Long-time contributor', 'Change level')
      cy.contains('Level changed to Regular.').should('be.visible')
      row('Second Member').should('contain.text', 'Regular')

      row('Second Member').find('button[aria-label="More actions"]').click()
      cy.contains('[role="menuitem"]', 'Lock level').click()
      confirm('Keep while we review', 'Lock')
      row('Second Member').should('contain.text', 'Locked')

      cy.contains('[role="radio"]', 'Regular').click()
      cy.get('[data-testid="trust-level-list"] [data-testid="moderation-row"]').should(
        'have.length',
        1,
      )

      cy.visit(`/g/community/${ids.community}/moderation`)
      cy.contains('button', 'Approval settings').click()
      cy.get('[data-testid="approval-level"]').should('be.visible').click()
      cy.contains('[role="option"]', 'New members').click()
      cy.contains('button', 'Save approval policy').click()
      cy.contains('Approval policy saved.').should('be.visible')

      cy.switchUser('secondMember')
      cy.visit('/g/submissions')
      cy.get('[data-testid="my-trust-level"]')
        .should('contain.text', 'Regular')
        .and('contain.text', 'To stay a Regular')
      cy.visit('/g/notifications')
      cy.contains('You are now a Regular').should('be.visible')

      cy.switchUser('member')
      cy.request({
        method: 'POST',
        url: '/api/method/gameplan.trust_levels.member_levels',
        failOnStatusCode: false,
      })
        .its('status')
        .should('eq', 403)
    })
  })
})
