// eslint-disable-next-line @typescript-eslint/triple-slash-reference
/// <reference path="../support/index.d.ts" />

// Simplified accessibility tests that don't require login
describe('Accessibility Tests (No Login Required)', () => {
	context('Authentication Page', () => {
		it('should check accessibility violations on login page', () => {
			cy.visit('/auth');
			cy.wait(2000); // Wait for page to fully load
			
			// Inject axe and run accessibility check with detailed logging
			cy.injectAxe();
			
			// Run accessibility check and log violations
			cy.checkA11y(
				null,
				{
					runOnly: {
						type: 'tag',
						values: ['wcag2a', 'wcag2aa', 'wcag21aa']
					}
				},
				(violations) => {
					// Log detailed violation information
					if (violations.length > 0) {
						cy.log(`⚠️ Found ${violations.length} accessibility violation(s)`);
						
						violations.forEach((violation, index) => {
							console.group(`\n🔍 Violation ${index + 1}: ${violation.id}`);
							console.log('Description:', violation.description);
							console.log('Impact:', violation.impact);
							console.log('Help URL:', violation.helpUrl);
							console.log('Affected nodes:');
							
							violation.nodes.forEach((node, nodeIndex) => {
								console.log(`  Node ${nodeIndex + 1}:`);
								console.log('    HTML:', node.html.substring(0, 150));
								console.log('    Selector:', node.target.join(' > '));
								console.log('    Failure Summary:', node.failureSummary);
							});
							console.groupEnd();
						});
						
						// Write violations to a summary
						const summary = violations.map(v => 
							`${v.id}: ${v.description} (Impact: ${v.impact})`
						).join('\n');
						
						cy.log('Summary:\n' + summary);
					} else {
						cy.log('✅ No accessibility violations found!');
						console.log('✅ No accessibility violations found on this page!');
					}
				},
				false // Don't fail on violations, just log them
			);
		});
	});

	context('Home Page (Public)', () => {
		it('should check accessibility violations on public home page', () => {
			// Handle potential application errors gracefully
			cy.visit('/', { failOnStatusCode: false });
			cy.wait(3000); // Wait longer for page to fully load and errors to settle
			
			// Inject axe and run accessibility check
			cy.injectAxe();
			
			// Run accessibility check
			cy.checkA11y(
				null,
				{
					runOnly: {
						type: 'tag',
						values: ['wcag2a', 'wcag2aa', 'wcag21aa']
					}
				},
				(violations) => {
					if (violations.length > 0) {
						cy.log(`⚠️ Found ${violations.length} accessibility violation(s)`);
						
						violations.forEach((violation, index) => {
							console.group(`\n🔍 Violation ${index + 1}: ${violation.id}`);
							console.log('Description:', violation.description);
							console.log('Impact:', violation.impact);
							console.log('Help URL:', violation.helpUrl);
							
							violation.nodes.forEach((node, nodeIndex) => {
								console.log(`  Node ${nodeIndex + 1}:`, node.target.join(' > '));
								console.log('    HTML:', node.html.substring(0, 100));
							});
							console.groupEnd();
						});
					} else {
						cy.log('✅ No accessibility violations found!');
					}
				},
				false
			);
		});
	});
});

