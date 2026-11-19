// Badges in the app (prd/badges.md): the Badges page, a badge's holders, the profile tab with
// favourites, the coins on the name card, the medallion's click, and Site administration.
// The rules are specced on the backend (gameplan/tests/features/test_badges.py); this walks
// what people see.
import { resetData } from '../../support/seed'

// frappe-ui's Checkbox keeps its input beside the label, joined by the label's `for`.
const checkbox = (label: string) =>
  cy
    .contains('label', label)
    .invoke('attr', 'for')
    .then((id) => cy.get(`[id="${id}"]`))

describe('Badges', () => {
  let profile: string

  beforeEach(() => {
    resetData('badges').then((ids) => {
      profile = String(ids.member_profile)
    })
  })

  it('lists badges by group and shows who earned one', () => {
    cy.loginAs('member')
    cy.visit('/g/badges')
    for (const group of ['Getting Started', 'Community', 'Posting']) {
      cy.contains('h2', group).should('exist')
    }
    cy.contains('a', 'Welcome').within(() => {
      cy.get('[aria-label="You have this badge"]').should('exist')
      cy.contains('1 person')
    })
    cy.contains('a', 'Welcome').click()
    cy.location('pathname').should('eq', '/g/badges/welcome')
    cy.contains('.body-container h1', 'Welcome').should('be.visible')
    cy.contains('Earned by').should('be.visible')
    cy.contains('a', 'Member').should('be.visible')
    cy.contains('a', 'Welcome thread').should('be.visible')
  })

  it('says what a badge is for and shines when hovered', () => {
    cy.loginAs('member')
    cy.visit('/g/badges')
    cy.get('button[aria-label="Reader, Bronze badge"]').trigger('mouseenter')
    cy.get('button[aria-label="Reader, Bronze badge"]').should(
      'have.class',
      'badge-medallion--playing',
    )
    // reka opens a tooltip on a mouse pointer moving over its trigger.
    cy.get('button[aria-label="Reader, Bronze badge"]').trigger('pointermove', {
      pointerType: 'mouse',
    })
    cy.contains('[role="tooltip"]', 'Read every reply in a discussion with more than 100 replies')
  })

  it('shines a medallion on click without following the link', () => {
    cy.loginAs('member')
    cy.visit('/g/badges')
    cy.get('button[aria-label="Welcome, Bronze badge"]').click()
    cy.get('button[aria-label="Welcome, Bronze badge"]').should(
      'have.class',
      'badge-medallion--playing',
    )
    cy.location('pathname').should('eq', '/g/badges')
    cy.get('button[aria-label="Welcome, Bronze badge"]').should(
      'not.have.class',
      'badge-medallion--playing',
    )
  })

  it('stars a favourite on your own profile', () => {
    cy.loginAs('member')
    cy.intercept('POST', '**/gameplan.badges.api.set_favorites').as('favorites')
    cy.visit(`/g/people/${profile}/badges`)
    cy.contains('[role="tab"], button', 'Badges').should('be.visible')
    cy.get('button[aria-label="Star Welcome"]').click()
    cy.wait('@favorites')
    cy.get('button[aria-label="Unstar Welcome"]').should('be.visible')
  })

  it('shows favourites on the name card for everyone who opens the profile', () => {
    cy.loginAs('member')
    cy.intercept('POST', '**/gameplan.badges.api.set_favorites').as('favorites')
    cy.visit(`/g/people/${profile}/badges`)
    cy.get('button[aria-label="Star Welcome"]').click()
    cy.wait('@favorites')

    cy.switchUser('secondMember')
    cy.visit(`/g/people/${profile}`)
    cy.get('[data-profile-badge-coins] button[aria-label="Welcome, Bronze badge"]')
      .as('coin')
      .trigger('mouseenter')
    cy.get('@coin').trigger('pointermove', { pointerType: 'mouse' })
    cy.contains('[role="tooltip"]', 'Earned')
  })

  it('lets a global admin turn a badge off', () => {
    cy.loginAs('admin')
    cy.visit('/g/admin-settings?tab=badges')
    checkbox('Use badges').should('be.checked')
    cy.get('input[aria-label="Search badges"]').type('reader')
    cy.get('[data-badge-row]').should('have.length', 1)
    cy.get('button[role="switch"][aria-label="Reader (Bronze)"]').click()
    cy.button('Save badges').click()
    cy.contains('Badges saved.').should('be.visible')
    cy.visit('/g/badges')
    cy.contains('a', 'Reader').should('not.exist')
    cy.contains('a', 'Welcome').should('be.visible')
  })
})
