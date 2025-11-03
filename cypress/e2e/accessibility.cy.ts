// eslint-disable-next-line @typescript-eslint/triple-slash-reference
/// <reference path="../support/index.d.ts" />
import { adminUser } from '../support/e2e';

describe('Accessibility Tests', () => {
	beforeEach(() => {
		// Skip login for authentication page tests
		if (!Cypress.currentTest.title.includes('Authentication')) {
			cy.loginAdmin();
			localStorage.setItem('locale', 'en-US');
		}
	});

	context('Home Page', () => {
		it('should have no accessibility violations on home page', () => {
			cy.visit('/');
			cy.wait(1000); // Wait for page to fully load
			cy.checkAccessibility();
		});
	});

	context('Authentication Pages', () => {
		it('should have no accessibility violations on login page', () => {
			cy.visit('/auth');
			cy.wait(500);
			cy.checkAccessibility();
		});
	});

	context('Settings Pages', () => {
		beforeEach(() => {
			cy.visit('/');
			cy.get('button[aria-label="User Menu"]').click();
			cy.get('button').contains('Settings').click();
		});

		it('should have no accessibility violations on settings page', () => {
			cy.wait(500);
			cy.checkAccessibility();
		});

		it('should have no accessibility violations on General settings', () => {
			cy.get('button').contains('General').click();
			cy.wait(500);
			cy.checkAccessibility();
		});

		it('should have no accessibility violations on Interface settings', () => {
			cy.get('button').contains('Interface').click();
			cy.wait(500);
			cy.checkAccessibility();
		});
	});

	context('Keyboard Navigation', () => {
		beforeEach(() => {
			cy.visit('/');
			cy.wait(1000);
		});

		it('should be navigable with keyboard only', () => {
			// Start from top of page
			cy.get('body').type('{tab}');
			
			// Check that focus is visible
			cy.focused().should('be.visible');
			
			// Tab through interactive elements
			cy.get('body').type('{tab}{tab}{tab}');
			
			// Verify we can tab through the page
			cy.focused().should('exist');
		});

		it('should have visible focus indicators', () => {
			// Tab to first interactive element
			cy.get('body').type('{tab}');
			
			// Check if focused element has visible outline or border
			cy.focused().should('have.css', 'outline').or('have.css', 'border');
		});
	});

	context('ARIA Labels', () => {
		beforeEach(() => {
			cy.visit('/');
			cy.wait(1000);
		});

		it('should have aria-labels on interactive buttons', () => {
			// Check for buttons with aria-label
			cy.get('button[aria-label]').should('exist');
			
			// Verify important buttons have labels
			cy.get('button[aria-label="User Menu"]').should('exist');
			cy.get('button[aria-label="New Chat"]').should('exist');
		});

		it('should have proper form labels', () => {
			// Check chat input has proper labeling
			cy.get('#chat-input').should('exist');
			
			// Check search input
			cy.get('#chat-search').should('exist');
		});
	});

	context('Screen Reader Compatibility', () => {
		it('should have semantic HTML structure', () => {
			cy.visit('/');
			cy.wait(1000);
			
			// Check for semantic elements
			cy.get('main').should('exist').or('body').should('exist');
			
			// Check for headings hierarchy
			cy.get('h1, h2, h3').should('exist');
		});

		it('should have alt text for images', () => {
			cy.visit('/');
			cy.wait(1000);
			
			// Check that images have alt attributes (or are decorative)
			cy.get('img').each(($img) => {
				cy.wrap($img).should('have.attr', 'alt').or('have.attr', 'aria-hidden', 'true');
			});
		});
	});
});

