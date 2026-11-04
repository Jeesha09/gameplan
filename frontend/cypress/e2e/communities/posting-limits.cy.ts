import { resetData } from '../../support/seed'

const configure = (enabled = 1) =>
  cy.request('POST', '/api/method/gameplan.posting_limits.save_settings', {
    enabled,
    discussions_hour: 1,
    discussions_day: 2,
    replies_hour: 1,
    replies_day: 2,
  })

describe('Site posting limits', () => {
  it('lets global admins configure limits in site-wide moderation', () => {
    resetData('onboarded')
    cy.visit('/g/moderation?scope=site&tab=posting-limits')
    cy.contains('h2', 'Posting limits').should('be.visible')
    cy.get('#moderation-sidebar [data-slot="sidebar-item"][data-state="active"]').should(
      'have.length',
      1,
    )
    cy.contains('button', 'Account suspensions').click()
    cy.contains('No active account suspensions.').should('be.visible')
    cy.contains('button', 'Posting limits').click()
    cy.contains('h2', 'Posting limits').should('be.visible')
    cy.get('[aria-label="Discussions per hour"]').should('have.value', '5').clear().type('3')
    cy.contains('button', /^Save$/).click()
    cy.contains('Posting limits saved').should('be.visible')
    cy.request('/api/method/gameplan.posting_limits.settings')
      .its('body.message.discussions_hour')
      .should('eq', 3)
    cy.switchUser('member')
    cy.visit('/g/moderation')
    cy.contains('button', /^Posting limits$/).should('not.exist')
  })

  it('keeps a limited reply draft and refreshes its wait on focus', () => {
    resetData('space_with_discussion').then((ids) => {
      configure()
      cy.loginAs('member')
      cy.visit(`/g/community/${ids.community}/space/${ids.space}/discussion/${ids.discussion}`)
      cy.contains('button', 'Add a comment').click()
      cy.get('[contenteditable=true]').click().type('My accepted reply')
      cy.contains('button:visible', /^\s*Submit\s*$/).click()
      cy.get('[data-id]').contains('My accepted reply').should('be.visible')
      cy.contains('button', 'Add a comment').click()
      cy.get('[contenteditable=true]').click().type('Keep my next reply draft')
      cy.get('[data-testid="posting-limit-status"]').should('contain.text', '1 reply per hour')
      cy.contains('button:visible', /^\s*Submit\s*$/).should('be.disabled')
      cy.window()
        .then((win) =>
          cy.request({
            method: 'POST',
            url: '/api/v2/document/GP Comment',
            failOnStatusCode: false,
            headers: { 'X-Frappe-CSRF-Token': (win as any).csrf_token },
            body: {
              reference_doctype: 'GP Discussion',
              reference_name: ids.discussion,
              content: 'Bypass',
            },
          }),
        )
        .its('status')
        .should('eq', 429)
      cy.get('[contenteditable=true]').should('contain.text', 'Keep my next reply draft')
      cy.task('requestAsUser', {
        user: 'Administrator',
        method: 'POST',
        path: '/api/method/gameplan.posting_limits.save_settings',
        body: {
          enabled: 0,
          discussions_hour: 1,
          discussions_day: 2,
          replies_hour: 1,
          replies_day: 2,
        },
      })
      cy.window().then((win) => win.dispatchEvent(new Event('focus')))
      cy.get('[data-testid="posting-limit-status"]').should('not.exist')
      cy.contains('button:visible', /^\s*Submit\s*$/)
        .should('not.be.disabled')
        .click()
      cy.get('[data-id]').contains('Keep my next reply draft').should('be.visible')
    })
  })
  it('shows the discussion wait without blocking draft editing or scheduling', () => {
    resetData('space_with_discussion').then((ids) => {
      configure()
      cy.loginAs('member')
      cy.visit(`/g/community/${ids.community}/new-discussion?spaceId=${ids.space}`)
      cy.get('textarea[placeholder="Title"]')
        .should('not.be.disabled')
        .type('Keep my discussion draft')
      cy.get('[contenteditable=true]').click().type('I can keep writing while limited')
      cy.get('[data-testid="posting-limit-status"]').should('contain.text', 'discussion per hour')
      cy.contains('button:visible', /^\s*Publish\s*$/).should('be.disabled')
      cy.get('[aria-label="More publish options"]').filter(':visible').click()
      cy.contains('[role="menuitem"]', 'Schedule for later').should(
        'not.have.attr',
        'aria-disabled',
        'true',
      )
      cy.get('textarea[placeholder="Title"]').should('have.value', 'Keep my discussion draft')
    })
  })
})
