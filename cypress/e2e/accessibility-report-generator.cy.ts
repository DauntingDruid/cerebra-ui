// eslint-disable-next-line @typescript-eslint/triple-slash-reference
/// <reference path="../support/index.d.ts" />

// Generate detailed accessibility report and save to file
describe('Accessibility Report Generator', () => {
	let allViolations: Array<{
		page: string;
		id: string;
		description: string;
		impact: string;
		helpUrl: string;
		nodes: Array<{
			selector: string;
			html: string;
			failureSummary: string;
		}>;
	}> = [];

	after(() => {
		// Generate markdown report
		let report = '# Accessibility Test Report\n\n';
		report += `**Generated:** ${new Date().toISOString()}\n\n`;
		report += `**Total Violations Found:** ${allViolations.length}\n\n`;

		if (allViolations.length > 0) {
			// Group violations by type
			const grouped: Record<string, typeof allViolations> = {};
			allViolations.forEach(v => {
				if (!grouped[v.id]) {
					grouped[v.id] = [];
				}
				grouped[v.id].push(v);
			});

			report += '## Summary by Violation Type\n\n';
			Object.entries(grouped).forEach(([id, violations]) => {
				const first = violations[0];
				const pages = [...new Set(violations.map(v => v.page))];
				report += `- **${id}** (${first.impact}) - Found ${violations.length} time(s) across ${pages.length} page(s)\n`;
				report += `  - ${first.description}\n`;
				report += `  - Pages: ${pages.join(', ')}\n\n`;
			});

			report += '---\n\n## Detailed Violations\n\n';

			// Group by page
			const byPage: Record<string, typeof allViolations> = {};
			allViolations.forEach(v => {
				if (!byPage[v.page]) {
					byPage[v.page] = [];
				}
				byPage[v.page].push(v);
			});

			Object.entries(byPage).forEach(([page, violations]) => {
				report += `### ${page}\n\n`;
				report += `**Total Violations:** ${violations.length}\n\n`;

				violations.forEach((v, idx) => {
					report += `#### Violation ${idx + 1}: ${v.id} (${v.impact})\n\n`;
					report += `**Description:** ${v.description}\n\n`;
					report += `**Help URL:** ${v.helpUrl}\n\n`;
					report += `**Affected Elements:** ${v.nodes.length}\n\n`;

					v.nodes.forEach((node, nodeIdx) => {
						report += `**Element ${nodeIdx + 1}:**\n`;
						report += `- Selector: \`${node.selector}\`\n`;
						report += `- Issue: ${node.failureSummary}\n`;
						report += `- HTML: \`${node.html.substring(0, 150)}${node.html.length > 150 ? '...' : ''}\`\n\n`;
					});

					report += '---\n\n';
				});
			});

			report += '## Recommendations\n\n';
			report += '1. Review each violation above\n';
			report += '2. Fix issues in source code\n';
			report += '3. Re-run tests to verify fixes\n';
			report += '4. Focus on Critical and Serious impact violations first\n\n';
		} else {
			report += '✅ **No accessibility violations found!**\n\n';
			report += 'Great job! Your application meets WCAG 2A, 2AA, and 2.1AA standards.\n';
		}

		// Write report to file using Cypress writeFile command
		cy.writeFile('frontend_test/accessibility-report.md', report).then(() => {
			console.log('\n📄 Accessibility report saved to: frontend_test/accessibility-report.md\n');
			
			// Also log summary to console
			console.log('\n' + '='.repeat(80));
			console.log('📋 ACCESSIBILITY REPORT SUMMARY');
			console.log('='.repeat(80));
			console.log(`Total violations: ${allViolations.length}`);
			if (allViolations.length > 0) {
				const grouped: Record<string, typeof allViolations> = {};
				allViolations.forEach(v => {
					if (!grouped[v.id]) grouped[v.id] = [];
					grouped[v.id].push(v);
				});
				console.log('\nViolations by type:');
				Object.entries(grouped).forEach(([id, violations]) => {
					console.log(`  - ${id}: ${violations.length} occurrence(s)`);
				});
			}
			console.log('='.repeat(80) + '\n');
		});
	});

	context('Authentication Page', () => {
		it('should check and record accessibility violations', () => {
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
							allViolations.push({
								page: 'Authentication Page',
								id: v.id,
								description: v.description,
								impact: v.impact || 'unknown',
								helpUrl: v.helpUrl,
								nodes: v.nodes.map(node => ({
									selector: node.target.join(' > '),
									html: node.html,
									failureSummary: node.failureSummary || ''
								}))
							});

							console.log(`\n🔍 [Authentication Page] ${v.id} (${v.impact})`);
							console.log(`   Description: ${v.description}`);
							console.log(`   Help: ${v.helpUrl}`);
							console.log(`   Elements: ${v.nodes.length}`);
						});
					} else {
						console.log('✅ Authentication page: No violations');
					}
				},
				true // skipFailures
			);
		});
	});

	context('Home Page', () => {
		it('should check and record accessibility violations', () => {
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
							allViolations.push({
								page: 'Home Page',
								id: v.id,
								description: v.description,
								impact: v.impact || 'unknown',
								helpUrl: v.helpUrl,
								nodes: v.nodes.map(node => ({
									selector: node.target.join(' > '),
									html: node.html,
									failureSummary: node.failureSummary || ''
								}))
							});

							console.log(`\n🔍 [Home Page] ${v.id} (${v.impact})`);
							console.log(`   Description: ${v.description}`);
							console.log(`   Help: ${v.helpUrl}`);
							console.log(`   Elements: ${v.nodes.length}`);
						});
					} else {
						console.log('✅ Home page: No violations');
					}
				},
				true // skipFailures
			);
		});
	});
});

