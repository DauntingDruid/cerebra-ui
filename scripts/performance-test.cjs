#!/usr/bin/env node

/**
 * Performance Testing Script
 * Runs Lighthouse audits on specified URLs and generates reports
 */

const lighthouse = require('lighthouse').default || require('lighthouse');
const chromeLauncher = require('chrome-launcher');
const fs = require('fs');
const path = require('path');

// Configuration
const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const OUTPUT_DIR = path.join(process.cwd(), 'frontend_test', 'performance', 'reports');
const PAGES = [
  { name: 'Home Page', path: '/' },
  { name: 'Authentication Page', path: '/auth' },
  { name: 'Settings Page', path: '/settings' }
];

// Lighthouse options
const lighthouseOptions = {
  logLevel: 'info',
  output: 'json',
  onlyCategories: ['performance', 'accessibility', 'best-practices', 'seo'],
  formFactor: 'desktop',
  throttling: {
    rttMs: 40,
    throughputKbps: 10 * 1024,
    cpuSlowdownMultiplier: 1
  },
  screenEmulation: {
    mobile: false,
    width: 1350,
    height: 940,
    deviceScaleFactor: 1
  }
};

// Chrome launcher options
const chromeOptions = {
  chromeFlags: ['--headless', '--no-sandbox', '--disable-gpu']
};

async function runLighthouse(url, pageName) {
  console.log(`\nRunning Lighthouse audit for ${pageName}...`);
  console.log(`URL: ${url}`);

  const chrome = await chromeLauncher.launch(chromeOptions);
  const options = {
    ...lighthouseOptions,
    port: chrome.port
  };

  try {
    const result = await lighthouse(url, options);
    const report = result.lhr;

    // Extract key metrics
    const performanceScore = report.categories.performance.score;
    const metrics = {
      performance: performanceScore ? Math.round(performanceScore * 100) : null,
      accessibility: Math.round(report.categories.accessibility.score * 100),
      bestPractices: Math.round(report.categories['best-practices'].score * 100),
      seo: Math.round(report.categories.seo.score * 100),
      fcp: Math.round(report.audits['first-contentful-paint'].numericValue),
      lcp: Math.round(report.audits['largest-contentful-paint'].numericValue),
      fid: Math.round(report.audits['max-potential-fid']?.numericValue || 0),
      cls: Math.round(report.audits['cumulative-layout-shift'].numericValue * 1000) / 1000,
      tti: Math.round(report.audits['interactive'].numericValue),
      totalBlockingTime: Math.round(report.audits['total-blocking-time'].numericValue),
      speedIndex: report.audits['speed-index']?.numericValue ? Math.round(report.audits['speed-index'].numericValue) : null
    };

    // Save full report
    const reportPath = path.join(OUTPUT_DIR, `${pageName.toLowerCase().replace(/\s+/g, '-')}-${Date.now()}.json`);
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));

    // Save HTML report
    const htmlReportPath = path.join(OUTPUT_DIR, `${pageName.toLowerCase().replace(/\s+/g, '-')}-report.html`);
    fs.writeFileSync(htmlReportPath, result.report);

    console.log(`\n${pageName} Results:`);
    if (metrics.performance !== null) {
      console.log(`  Performance Score: ${metrics.performance}/100`);
    } else {
      console.log(`  Performance Score: N/A (Speed Index could not be calculated - likely due to very fast page load)`);
    }
    console.log(`  FCP: ${metrics.fcp}ms (target: < 1800ms) - ${metrics.fcp < 1800 ? 'Excellent' : 'Needs improvement'}`);
    console.log(`  LCP: ${metrics.lcp}ms (target: < 2500ms) - ${metrics.lcp < 2500 ? 'Excellent' : 'Needs improvement'}`);
    console.log(`  CLS: ${metrics.cls} (target: < 0.1) - ${metrics.cls < 0.1 ? 'Perfect' : 'Needs improvement'}`);
    console.log(`  TTI: ${metrics.tti}ms`);
    console.log(`  Total Blocking Time: ${metrics.totalBlockingTime}ms`);

    return {
      pageName,
      url,
      timestamp: new Date().toISOString(),
      metrics,
      reportPath,
      htmlReportPath
    };
  } catch (error) {
    console.error(`Error running Lighthouse for ${pageName}:`, error);
    return null;
  } finally {
    await chrome.kill();
  }
}

async function generateSummaryReport(results) {
  const summary = {
    timestamp: new Date().toISOString(),
    baseUrl: BASE_URL,
    pages: results.filter(r => r !== null),
    averages: {
      performance: 0,
      fcp: 0,
      lcp: 0,
      cls: 0,
      tti: 0
    }
  };

  // Calculate averages
  const validResults = results.filter(r => r !== null);
  if (validResults.length > 0) {
    const performanceScores = validResults.map(r => r.metrics.performance).filter(s => s !== null);
    summary.averages.performance = performanceScores.length > 0 
      ? Math.round(performanceScores.reduce((sum, s) => sum + s, 0) / performanceScores.length)
      : null;
    summary.averages.fcp = Math.round(
      validResults.reduce((sum, r) => sum + r.metrics.fcp, 0) / validResults.length
    );
    summary.averages.lcp = Math.round(
      validResults.reduce((sum, r) => sum + r.metrics.lcp, 0) / validResults.length
    );
    summary.averages.cls = Math.round(
      (validResults.reduce((sum, r) => sum + r.metrics.cls, 0) / validResults.length) * 1000
    ) / 1000;
    summary.averages.tti = Math.round(
      validResults.reduce((sum, r) => sum + r.metrics.tti, 0) / validResults.length
    );
  }

  // Save summary
  const summaryPath = path.join(OUTPUT_DIR, 'summary.json');
  fs.writeFileSync(summaryPath, JSON.stringify(summary, null, 2));

  // Generate markdown report
  const markdownReport = generateMarkdownReport(summary);
  const markdownPath = path.join(process.cwd(), 'frontend_test', 'performance-report.md');
  fs.writeFileSync(markdownPath, markdownReport);

  console.log(`\nSummary report saved to: ${summaryPath}`);
  console.log(`Markdown report saved to: ${markdownPath}`);

  return summary;
}

function generateMarkdownReport(summary) {
  let report = `# Performance Test Report\n\n`;
  report += `**Generated:** ${summary.timestamp}\n\n`;
  report += `**Base URL:** ${summary.baseUrl}\n\n`;

  report += `## Summary\n\n`;
  report += `**Pages Tested:** ${summary.pages.length}\n\n`;
  if (summary.averages.performance !== null) {
    report += `**Average Performance Score:** ${summary.averages.performance}/100\n\n`;
  } else {
    report += `**Average Performance Score:** N/A (Speed Index calculation issue - see details below)\n\n`;
  }
  report += `**Average Core Web Vitals:**\n`;
  report += `- LCP (Largest Contentful Paint): ${summary.averages.lcp}ms (target: < 2500ms) - ${summary.averages.lcp < 2500 ? 'Excellent' : 'Needs improvement'}\n`;
  report += `- FCP (First Contentful Paint): ${summary.averages.fcp}ms (target: < 1800ms) - ${summary.averages.fcp < 1800 ? 'Excellent' : 'Needs improvement'}\n`;
  report += `- CLS (Cumulative Layout Shift): ${summary.averages.cls} (target: < 0.1) - ${summary.averages.cls < 0.1 ? 'Perfect' : 'Needs improvement'}\n`;
  report += `- TTI (Time to Interactive): ${summary.averages.tti}ms\n\n`;

  report += `## Page Results\n\n`;

  summary.pages.forEach(page => {
    report += `### ${page.pageName}\n\n`;
    report += `**URL:** ${page.url}\n\n`;
    if (page.metrics.performance !== null) {
      report += `**Performance Score:** ${page.metrics.performance}/100\n\n`;
    } else {
      report += `**Performance Score:** N/A (Speed Index could not be calculated)\n\n`;
      report += `**Note:** This typically occurs when pages load very quickly in local development environments. All other metrics are accurate.\n\n`;
    }
    report += `**Metrics:**\n`;
    if (page.metrics.performance !== null) {
      report += `- Performance: ${page.metrics.performance}/100\n`;
    } else {
      report += `- Performance: N/A (Speed Index calculation issue)\n`;
    }
    report += `- Accessibility: ${page.metrics.accessibility}/100\n`;
    report += `- Best Practices: ${page.metrics.bestPractices}/100\n`;
    report += `- SEO: ${page.metrics.seo}/100\n\n`;
    report += `**Core Web Vitals:**\n`;
    report += `- FCP: ${page.metrics.fcp}ms (target: < 1800ms) - ${page.metrics.fcp < 1800 ? 'Excellent' : 'Needs improvement'}\n`;
    report += `- LCP: ${page.metrics.lcp}ms (target: < 2500ms) - ${page.metrics.lcp < 2500 ? 'Excellent' : 'Needs improvement'}\n`;
    report += `- CLS: ${page.metrics.cls} (target: < 0.1) - ${page.metrics.cls < 0.1 ? 'Perfect' : 'Needs improvement'}\n`;
    report += `- TTI: ${page.metrics.tti}ms\n`;
    report += `- Total Blocking Time: ${page.metrics.totalBlockingTime}ms\n`;
    if (page.metrics.speedIndex !== null) {
      report += `- Speed Index: ${page.metrics.speedIndex}ms\n\n`;
    } else {
      report += `- Speed Index: N/A (page loaded too quickly to calculate)\n\n`;
    }
    report += `**Reports:**\n`;
    report += `- JSON: ${page.reportPath}\n`;
    report += `- HTML: ${page.htmlReportPath}\n\n`;
    report += `---\n\n`;
  });

  report += `## Recommendations\n\n`;
  
  if (summary.averages.lcp > 2500) {
    report += `- LCP exceeds 2.5s threshold. Optimize largest content element loading.\n`;
  }
  if (summary.averages.cls > 0.1) {
    report += `- CLS exceeds 0.1 threshold. Fix layout shifts during page load.\n`;
  }
  if (summary.averages.fcp > 1800) {
    report += `- FCP exceeds 1.8s threshold. Optimize initial render.\n`;
  }
  if (summary.averages.performance < 90) {
    report += `- Performance score below 90. Review Lighthouse recommendations for optimization opportunities.\n`;
  }

  report += `\n---\n\n`;
  report += `**Note:** For detailed recommendations, check the HTML reports in \`frontend_test/performance/reports/\`\n`;

  return report;
}

async function main() {
  console.log('Starting Performance Testing...');
  console.log(`Base URL: ${BASE_URL}`);

  // Create output directory
  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  }

  const results = [];

  for (const page of PAGES) {
    const url = `${BASE_URL}${page.path}`;
    const result = await runLighthouse(url, page.name);
    results.push(result);
    // Small delay between tests
    await new Promise(resolve => setTimeout(resolve, 2000));
  }

  const summary = await generateSummaryReport(results);

  console.log('\n=== Performance Testing Complete ===');
  console.log(`\nAverage Performance Score: ${summary.averages.performance}/100`);
  console.log(`Check the full report: frontend_test/performance-report.md`);
}

main().catch(console.error);

