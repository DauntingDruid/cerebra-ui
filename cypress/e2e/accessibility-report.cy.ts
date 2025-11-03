// eslint-disable-next-line @typescript-eslint/triple-slash-reference
/// <reference path="../support/index.d.ts" />

// Generate detailed accessibility report
describe('Accessibility Report', () => {
	let allViolations: any[] = [];

	after(() => {
		// Generate summary report
		if (allViolations.length > 0) {
			console.log('\n' + '='.repeat(80));
			console.log('📋 ACCESSIBILITY TEST SUMMARY');
			console.log('='.repeat(80));
			console.log(`Total violations found: ${allViolations.length}\n`);
			
			// Group by violation type
			const grouped = allViolations.reduce((acc, v) => {
				if (!acc[v.id]) {
					acc[v.id] = {
						id: v.id,
						description: v.description,
						impact: v.impact,
						count: 0,
						pages: new Set()
					};
				}
				acc[v.id].count++;
				acc[v.id].pages.add(v.page);
				return acc;
			}, {} as any);

			console.log('Violations by Type:');
			Object.values(grouped).forEach((g: any) => {
				console.log(`\n  ${g.id} (${g.impact}) - Found ${g.count} time(s)`);
				console.log(`    Description: ${g.description}`);
				console.log(`    Pages: ${Array.from(g.pages).join(', ')}`);
			});

			console.log('\n' + '='.repeat(80));
			console.log('💡 Next Steps:');
			console.log('1. Review each violation in the detailed logs above');
			console.log('2. Fix issues in the source code');
			console.log('3. Re-run tests to verify fixes');
			console.log('='.repeat(80) + '\n');
		} else {
			console.log('\n✅ No accessibility violations found! Great job!\n');
		}
	});

	context('Authentication Page', () => {
		it('should generate accessibility report for login page', () => {
			cy.visit('/auth');
			cy.wait(2000);
			
			cy.injectAxe();
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
						violations.forEach(v => {
							v.page = 'Authentication Page';
							allViolations.push(v);
						});
						
						// Log detailed violations
						console.log('\n' + '='.repeat(80));
						console.log('🔍 ACCESSIBILITY VIOLATIONS - Authentication Page');
						console.log('='.repeat(80));
						violations.forEach((v, idx) => {
							console.log(`\nViolation ${idx + 1}: ${v.id} (${v.impact})`);
							console.log(`  Description: ${v.description}`);
							console.log(`  Help: ${v.helpUrl}`);
							console.log(`  Affected Elements (${v.nodes.length}):`);
							v.nodes.forEach((node, nodeIdx) => {
								console.log(`    ${nodeIdx + 1}. Selector: ${node.target.join(' > ')}`);
								console.log(`       HTML: ${node.html.substring(0, 100)}...`);
								console.log(`       Issue: ${node.failureSummary}`);
							});
						});
						console.log('='.repeat(80) + '\n');
						
						cy.log(`Found ${violations.length} violation(s) - see console for details`);
					} else {
						console.log('✅ Authentication page: No violations found');
						cy.log('✅ No accessibility violations found!');
					}
				},
				true // skipFailures = true, don't fail the test
			);
		});
	});

	context('Home Page', () => {
		it('should generate accessibility report for home page', () => {
			cy.visit('/', { failOnStatusCode: false });
			cy.wait(3000);
			
			cy.injectAxe();
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
						violations.forEach(v => {
							v.page = 'Home Page';
							allViolations.push(v);
						});
						
						// Log detailed violations
						console.log('\n' + '='.repeat(80));
						console.log('🔍 ACCESSIBILITY VIOLATIONS - Home Page');
						console.log('='.repeat(80));
						violations.forEach((v, idx) => {
							console.log(`\nViolation ${idx + 1}: ${v.id} (${v.impact})`);
							console.log(`  Description: ${v.description}`);
							console.log(`  Help: ${v.helpUrl}`);
							console.log(`  Affected Elements (${v.nodes.length}):`);
							v.nodes.forEach((node, nodeIdx) => {
								console.log(`    ${nodeIdx + 1}. Selector: ${node.target.join(' > ')}`);
								console.log(`       HTML: ${node.html.substring(0, 100)}...`);
								console.log(`       Issue: ${node.failureSummary}`);
							});
						});
						console.log('='.repeat(80) + '\n');
						
						cy.log(`Found ${violations.length} violation(s) - see console for details`);
					} else {
						console.log('✅ Home page: No violations found');
						cy.log('✅ No accessibility violations found!');
					}
				},
				true // skipFailures = true, don't fail the test
			);
		});
	});
});

