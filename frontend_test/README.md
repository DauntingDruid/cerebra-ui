# Frontend Unit Tests

This directory contains all frontend unit tests for the CerebraUI project. Tests are completely separated from the main source code (`src/` directory).

## Directory Structure

```
frontend_test/
├── utils/              # Tests for utility functions
│   ├── utils-validation.test.ts
│   ├── utils-text-processing.test.ts
│   ├── utils-frontmatter.test.ts
│   └── utils-chat-validation.test.ts
├── apis/               # Tests for API functions
│   ├── auths.test.ts
│   └── workflows.test.ts
├── stores/             # Tests for Svelte stores
│   └── theme.test.ts
├── setup/              # Test setup and configuration
│   └── setup.ts
└── README.md           # This file
```

## Running Tests

### Run all tests
```bash
npm run test:frontend
```

### Run tests in watch mode (auto-rerun on changes)
```bash
npm run test:frontend -- --watch
```

### Run specific test file
```bash
npm run test:frontend -- frontend_test/utils/utils-validation.test.ts
```

### Run with coverage report
```bash
npm run test:frontend -- --coverage
```

## Test Coverage

Current test coverage includes:

### Utility Functions
- URL validation (`isValidHttpUrl`)
- Text processing (`removeEmojis`, `removeFormattings`, `cleanText`)
- Frontmatter extraction (`extractFrontmatter`)
- Chat validation (`convertOpenAIChats`)

### API Functions
- Authentication APIs (`userSignIn`, `userSignUp`) - with fetch mocking
- Workflow APIs (`createNewWorkflow`, `getWorkflows`, etc.) - with fetch mocking

### Store Management
- Theme store state management

## Test Organization Principles

1. **Separation**: All tests are in `frontend_test/` directory, completely separate from `src/`
2. **Organization**: Tests are grouped by module (utils, apis, stores)
3. **Naming**: Test files follow pattern `[module]-[feature].test.ts`
4. **Imports**: Tests import from `src/` using relative paths (e.g., `../../src/lib/utils/index`)

## Adding New Tests

When adding new tests:

1. Create test file in appropriate subdirectory (`utils/`, `apis/`, `stores/`)
2. Use `.test.ts` extension
3. Import source code from `../../src/...`
4. Follow existing test structure:
   - Use `describe()` blocks for grouping
   - Use descriptive `it()` test names
   - Mock external dependencies (APIs, browser APIs)

## Example Test Structure

```typescript
import { describe, it, expect } from 'vitest';
import { functionToTest } from '../../src/lib/utils/index';

describe('functionToTest', () => {
  it('should do something correctly', () => {
    expect(functionToTest('input')).toBe('expected output');
  });
});
```

## Dependencies

Tests use:
- **Vitest** - Test runner
- **Svelte** - For testing Svelte stores
- Native Node.js environment (no browser/DOM required for most tests)

## Notes

- All tests are written in English
- Tests focus on unit testing individual functions and components
- Integration/E2E tests are in `cypress/` directory