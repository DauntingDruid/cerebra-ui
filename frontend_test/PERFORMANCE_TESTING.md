# Performance Testing Guide

## Overview

Performance testing measures how fast and responsive your application is. This is a logical next step after completing:
- UX Testing
- Unit Testing
- Accessibility Testing

## What to Test

### Core Web Vitals (Google's Key Metrics)

1. **LCP (Largest Contentful Paint)** - Loading performance
   - Target: < 2.5 seconds
   - Measures: Time to render the largest content element

2. **FID (First Input Delay)** - Interactivity
   - Target: < 100 milliseconds
   - Measures: Time from user interaction to browser response

3. **CLS (Cumulative Layout Shift)** - Visual stability
   - Target: < 0.1
   - Measures: Visual stability during page load

### Additional Metrics

- **TTFB (Time to First Byte)** - Server response time
- **FCP (First Contentful Paint)** - Initial render
- **TTI (Time to Interactive)** - Page interactivity
- **Total Load Time** - Complete page load
- **Bundle Size** - JavaScript bundle sizes

## Recommended Tools

### 1. Lighthouse (Recommended for Start)

**What it is:** Google's automated tool for performance auditing

**How to use:**
- Built into Chrome DevTools
- Can run via CLI
- Provides scores and recommendations

**Setup:**
```bash
npm install --save-dev lighthouse
```

**Run:**
```bash
# Via Chrome DevTools: F12 > Lighthouse tab > Run
# Or via CLI:
npx lighthouse http://localhost:8080 --view
```

### 2. Cypress Performance Plugin

**What it is:** Performance testing within Cypress

**Setup:**
```bash
npm install --save-dev cypress-performance
```

### 3. Web Vitals Library

**What it is:** Real User Monitoring (RUM) for Web Vitals

**Setup:**
```bash
npm install web-vitals
```

### 4. Bundle Analysis

**What it is:** Analyze bundle sizes

**Tools:**
- `vite-bundle-visualizer` (for Vite projects)
- `webpack-bundle-analyzer` (if using webpack)

## Testing Approach

### Phase 1: Baseline Measurement

1. Run Lighthouse on key pages:
   - Home page
   - Authentication page
   - Main application pages

2. Record initial scores:
   - Performance score
   - Core Web Vitals
   - Load times

### Phase 2: Identify Issues

1. Review Lighthouse recommendations
2. Check bundle sizes
3. Identify slow API calls
4. Find render-blocking resources

### Phase 3: Optimization

1. Fix identified issues:
   - Code splitting
   - Image optimization
   - Lazy loading
   - Caching strategies

### Phase 4: Verification

1. Re-run tests
2. Compare before/after metrics
3. Document improvements

## Implementation Steps

### Step 1: Install Dependencies

```bash
npm install --save-dev lighthouse
```

### Step 2: Create Performance Test Script

Create `cypress/e2e/performance.cy.ts` to test page load times and interactivity.

### Step 3: Set Up Monitoring

Add Web Vitals tracking to monitor real user performance.

### Step 4: Create Performance Budget

Define acceptable limits:
- Max bundle size: 500KB
- Max LCP: 2.5s
- Max FID: 100ms
- Max CLS: 0.1

## Example Test Structure

```
frontend_test/
├── performance/
│   ├── lighthouse-reports/
│   ├── web-vitals/
│   └── bundle-analysis/
└── PERFORMANCE_TESTING.md
```

## Expected Deliverables

1. Performance test scripts
2. Baseline performance report
3. Optimization recommendations
4. Final performance report with improvements
5. Performance budget documentation

## Resources

- [Web.dev Performance](https://web.dev/performance/)
- [Core Web Vitals](https://web.dev/vitals/)
- [Lighthouse Documentation](https://developers.google.com/web/tools/lighthouse)
- [Vite Performance Guide](https://vitejs.dev/guide/performance.html)

## Next Steps

1. Install Lighthouse
2. Run initial performance audit
3. Document baseline metrics
4. Identify optimization opportunities
5. Implement fixes
6. Re-test and verify improvements

---

**Last Updated:** 2025-11-03

