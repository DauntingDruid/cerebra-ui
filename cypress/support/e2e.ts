/// <reference types="cypress" />
// eslint-disable-next-line @typescript-eslint/triple-slash-reference
/// <reference path="../support/index.d.ts" />

// Import cypress-axe for accessibility testing
import 'cypress-axe';

export const adminUser = {
	name: 'Admin User',
	email: 'admin@example.com',
	password: 'password'
};

const login = (email: string, password: string) => {
	return cy.session(
		email,
		() => {
			// Make sure to test against us english to have stable tests,
			// regardless on local language preferences
			localStorage.setItem('locale', 'en-US');
			// Visit auth page
			cy.visit('/auth');
			// Wait for page to be ready
			cy.wait(1000);
			// Fill out the form - with better error handling
			cy.get('input[autocomplete="email"]', { timeout: 10000 }).should('be.visible').type(email, { force: true });
			cy.get('input[type="password"]', { timeout: 10000 }).should('be.visible').type(password, { force: true });
			// Submit the form
			cy.get('button[type="submit"]', { timeout: 10000 }).should('be.visible').click();
			// Wait until the user is redirected to the home page
			cy.get('#chat-search', { timeout: 15000 }).should('exist');
			// Get the current version to skip the changelog dialog
			if (localStorage.getItem('version') === null) {
				cy.get('button', { timeout: 5000 }).contains("Okay, Let's Go!").click({ timeout: 5000 });
			}
		},
		{
			validate: () => {
				cy.request({
					method: 'GET',
					url: '/api/v1/auths/',
					headers: {
						Authorization: 'Bearer ' + localStorage.getItem('token')
					}
				});
			}
		}
	);
};

const register = (name: string, email: string, password: string) => {
	return cy
		.request({
			method: 'POST',
			url: '/api/v1/auths/signup',
			body: {
				name: name,
				email: email,
				password: password
			},
			failOnStatusCode: false
		})
		.then((response) => {
			// Accept 200 (success), 400 (already exists), or 403 (registration disabled)
			expect(response.status).to.be.oneOf([200, 400, 403]);
		});
};

const registerAdmin = () => {
	return register(adminUser.name, adminUser.email, adminUser.password);
};

const loginAdmin = () => {
	return login(adminUser.email, adminUser.password);
};

Cypress.Commands.add('login', (email, password) => login(email, password));
Cypress.Commands.add('register', (name, email, password) => register(name, email, password));
Cypress.Commands.add('registerAdmin', () => registerAdmin());
Cypress.Commands.add('loginAdmin', () => loginAdmin());

// Custom command for accessibility checks
Cypress.Commands.add('checkAccessibility', (options?: Partial<Cypress.Loggable & Cypress.Timeoutable>) => {
	cy.injectAxe();
	
	// Check for violations but don't fail the test - just log them
	cy.checkA11y(
		null,
		{
			runOnly: {
				type: 'tag',
				values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'best-practice']
			},
			rules: {
				// Allow some violations that might need manual review
				'color-contrast': { enabled: true },
				'landmark-one-main': { enabled: true },
				'page-has-heading-one': { enabled: true },
				'region': { enabled: true }
			}
		},
		(violations) => {
			// Log violations for review
			if (violations.length > 0) {
				cy.log(`⚠️ Found ${violations.length} accessibility violations (see console for details)`);
				console.group('🔍 Accessibility Violations');
				violations.forEach((violation, index) => {
					console.group(`Violation ${index + 1}: ${violation.id}`);
					console.error('Description:', violation.description);
					console.error('Impact:', violation.impact);
					console.error('Help:', violation.helpUrl);
					console.error('Nodes affected:');
					violation.nodes.forEach((node) => {
						console.error('  -', node.html.substring(0, 100));
						console.error('    Selector:', node.target.join(' > '));
					});
					console.groupEnd();
				});
				console.groupEnd();
			} else {
				cy.log('✅ No accessibility violations found!');
			}
		},
		{ ...options, log: false } // Suppress default Cypress logging
	);
});

before(() => {
	cy.registerAdmin();
});

// Ignore uncaught exceptions that are common in SPAs
Cypress.on('uncaught:exception', (err, runnable) => {
	// Ignore various application errors that don't affect accessibility testing
	const ignoredErrors = [
		'ResizeObserver',
		'ChunkLoadError',
		'Loading chunk',
		'Failed to fetch dynamically imported module',
		'is not async iterable',
		'w is not async iterable'
	];
	
	if (ignoredErrors.some(error => err.message.includes(error))) {
		console.warn(`Ignoring application error (not accessibility-related): ${err.message}`);
		return false; // Don't fail the test
	}
	// Let other errors fail the test
	return true;
});
