import { resetData } from '../../support/seed'

describe('Forum feature integration', () => {
  it('renders a public thread and its replies without Vue errors', () => {
    resetData('public_space').then((ids) => {
      const errors: string[] = []
      cy.clearCookies()
      cy.visit(`/g/community/${ids.community}/space/${ids.space}/discussion/${ids.discussion}`, {
        onBeforeLoad(win) {
          const original = win.console.error.bind(win.console)
          win.console.error = (...args) => {
            errors.push(args.map((value) => value?.stack || String(value)).join(' '))
            original(...args)
          }
        },
      })
      cy.contains('Welcome to Open Source').should('be.visible')
      cy.then(() => expect(errors, JSON.stringify(errors)).to.deep.eq([]))
      cy.contains('Glad to be here.').should('be.visible')
    })
  })
})

it('shows accepted answers and references together with discussion notifications', () => {
  resetData('space_with_discussion').then((ids) => {
    cy.switchUser('secondMember')
    cy.request('POST', '/api/v2/document/GP Comment', {
      reference_doctype: 'GP Discussion',
      reference_name: ids.discussion,
      content: '<p>The answer for the forum presentation.</p>',
    }).then(({ body }) => {
      const comment = String(body.data.name)
      cy.switchUser('member')
      cy.request(
        'POST',
        `/api/v2/document/GP Discussion/${ids.discussion}/method/highlight_comment`,
        {
          comment,
        },
      )
      cy.request('POST', '/api/v2/document/GP Discussion', {
        title: 'A related forum discussion',
        project: ids.space,
        content: `<p>See <a href="/g/community/${ids.community}/space/${ids.space}/discussion/${ids.discussion}">the original discussion</a>.</p>`,
      })
      cy.visit(`/g/community/${ids.community}/space/${ids.space}/discussion/${ids.discussion}`)
      cy.contains('Accepted answer').should('be.visible')
      cy.contains('The answer for the forum presentation.').should('be.visible')
      cy.get('button[aria-label="Discussion Options"]').first().click()
      cy.contains('[role="menuitem"]', 'References').click()
      cy.get('[role="dialog"]').contains('A related forum discussion').should('be.visible')
    })
  })
})

it('censors an accepted answer without changing its stored original', () => {
  resetData('space_with_discussion').then((ids) => {
    cy.switchUser('secondMember')
    cy.request('POST', '/api/v2/document/GP Comment', {
      reference_doctype: 'GP Discussion',
      reference_name: ids.discussion,
      content: '<p>forumsecret answer</p>',
    }).then(({ body }) => {
      const comment = String(body.data.name)
      cy.switchUser('member')
      cy.request(
        'POST',
        `/api/v2/document/GP Discussion/${ids.discussion}/method/highlight_comment`,
        { comment },
      )
      cy.switchUser('admin')
      cy.request('POST', '/api/method/gameplan.watched_words.add', {
        community: ids.community,
        action: 'Censor',
        word: 'forumsecret',
      })
      cy.request(`/api/v2/document/GP Discussion/${ids.discussion}`)
        .its('body.data.highlighted_reply.content')
        .should('eq', '■■■■■■■■■■■ answer')
      cy.visit(`/g/community/${ids.community}/space/${ids.space}/discussion/${ids.discussion}`)
      cy.contains('Accepted answer').should('be.visible')
      cy.contains('■■■■■■■■■■■ answer').should('be.visible')
      cy.switchUser('secondMember')
      cy.request(
        `/api/method/gameplan.watched_word_edits.original?doctype=GP Comment&name=${comment}`,
      )
        .its('body.message.content')
        .should('include', 'forumsecret answer')
    })
  })
})

it('queues a reply edit through the unified draft API', () => {
  resetData('space_with_discussion').then((ids) => {
    cy.switchUser('member')
    cy.request('POST', '/api/v2/document/GP Comment', {
      reference_doctype: 'GP Discussion',
      reference_name: ids.discussion,
      content: '<p>Original reply for editing</p>',
    }).then(({ body }) => {
      const comment = String(body.data.name)
      cy.switchUser('admin')
      cy.request('POST', '/api/method/gameplan.watched_words.add', {
        community: ids.community,
        action: 'Require approval',
        word: 'reviewreply',
      })
      cy.switchUser('member')
      cy.visit(`/g/community/${ids.community}/space/${ids.space}/discussion/${ids.discussion}`)
      cy.get(`[data-id="${comment}"] button[aria-label="Comment Options"]`).click()
      cy.contains('[role="menuitem"]', /^Edit$/).click()
      cy.get('[contenteditable=true]').click().type('{selectall}reviewreply proposed edit')
      cy.contains('button', /^\s*Submit\s*$/).click()
      cy.contains('Edit submitted for moderator approval').should('be.visible')
      cy.contains('p', 'Original reply for editing').should('be.visible')
      cy.request(`/api/v2/document/GP Comment/${comment}`)
        .its('body.data.content')
        .should('include', 'Original reply for editing')
    })
  })
})
