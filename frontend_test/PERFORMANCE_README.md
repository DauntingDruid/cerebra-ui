# Performance Testing Quick Start

## Setup Complete

Performance testing tools have been installed and configured.

## Quick Commands

### Run Full Performance Test
```bash
npm run test:performance
```

This will:
- Test multiple pages (Home, Auth, Settings)
- Generate detailed reports
- Create summary report in `frontend_test/performance-report.md`
- Save individual reports in `frontend_test/performance/reports/`

### Quick Performance Check
```bash
npm run test:performance:quick
```

Opens Lighthouse report for home page in browser.

## Prerequisites

Before running tests, ensure your application server is running:

```bash
# If using Docker
docker-compose up -d

# Or if using dev server
npm run dev
```

The script defaults to `http://localhost:3000`. To use a different URL:

```bash
BASE_URL=http://localhost:8080 npm run test:performance
```

## Output Files

- `frontend_test/performance-report.md` - Main summary report
- `frontend_test/performance/reports/*.json` - Detailed JSON reports
- `frontend_test/performance/reports/*.html` - Interactive HTML reports

## Metrics Measured

### Core Web Vitals
- **LCP (Largest Contentful Paint)** - Target: < 2.5s
- **FID (First Input Delay)** - Target: < 100ms
- **CLS (Cumulative Layout Shift)** - Target: < 0.1

### Additional Metrics
- Performance Score (0-100)
- FCP (First Contentful Paint)
- TTI (Time to Interactive)
- Total Blocking Time
- Speed Index

## Next Steps

1. Run baseline test to establish current performance
2. Review recommendations in HTML reports
3. Implement optimizations
4. Re-run tests to verify improvements

---

For detailed information, see `PERFORMANCE_TESTING.md`

