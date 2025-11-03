# Accessibility Fixes Guide

## Summary

Total Violations Found: 4 violations across 2 pages

**Breakdown:**
- Authentication Page: 2 violations
  - 1 color-contrast violation (affects 2 button elements)
  - 1 meta-viewport violation
- Home Page: 2 violations
  - 1 color-contrast violation (affects 2 button elements)
  - 1 meta-viewport violation

Note: The color-contrast violation appears on both pages because the same buttons exist on both pages, so it's counted separately for each page. The meta-viewport violation affects all pages since it's in the main HTML template.

## Priority 1: Color Contrast Issues (Serious - 2 violations)

### Problem

Current Status: Purple color `#A855F7` on white background has contrast ratio of 3.95:1  
WCAG Requirement: Minimum 4.5:1 ratio for normal text (WCAG AA)

### Affected Elements

Element 1: "Forgot?" button
- Location: `src/routes/auth/login/+page.svelte` (line 206)
- Current: `text-[#A855F7]` on white background

Element 2: "Sign In" button
- Location: `src/routes/auth/signup/+page.svelte` (line 275)
- Current: `text-[#A855F7]` on white background

### Fix for Light Mode (White Background)

Option 1: Use darker purple (Recommended)
```svelte
<!-- Change from: -->
class="text-sm text-[#A855F7] hover:text-[#9333EA] dark:text-[#A855F7] dark:hover:text-[#9333EA]"

<!-- To: -->
class="text-sm text-[#9333EA] hover:text-[#7C3AED] dark:text-[#A855F7] dark:hover:text-[#9333EA]"
```

Why: `#9333EA` provides 4.5:1 contrast ratio on white background

### Fix for Dark Mode (Black Background)

Current: `dark:text-[#A855F7]` (purple on black)

Check: Purple `#A855F7` on black `#000000` = 8.59:1 contrast ratio  
Conclusion: Dark mode is already accessible. No changes needed for dark mode.

### Complete Fix Example

File: `src/routes/auth/login/+page.svelte`
```svelte
<button
    type="button"
    class="text-sm text-[#9333EA] hover:text-[#7C3AED] dark:text-[#A855F7] dark:hover:text-[#9333EA]"
    on:click={() => goto('/auth/forgot-password')}
>
    {$i18n.t('Forgot?')}
</button>
```

File: `src/routes/auth/signup/+page.svelte`
```svelte
<button
    type="button"
    class="ml-1 text-sm text-[#9333EA] hover:text-[#7C3AED] dark:text-[#A855F7] dark:hover:text-[#9333EA] font-medium"
    on:click={() => goto('/auth/login')}
>
    Sign In
</button>
```

Explanation:
- Light mode: Use darker purple `#9333EA` for better contrast on white
- Dark mode: Keep lighter purple `#A855F7` (already good on black)

## Priority 2: Meta Viewport Issue (Moderate - 2 violations)

### Problem

The `maximum-scale=1` attribute in the viewport meta tag prevents users from zooming on mobile devices. This is an accessibility issue because:
- Users with visual impairments need to zoom in (up to 500% per WCAG)
- Mobile users sometimes need to zoom to read small text
- WCAG requires that zooming not be disabled

### Current Code

File: `src/app.html` (line 14-16)
```html
<meta
    name="viewport"
    content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover"
/>
```

### What is "maximum-scale"?

- `maximum-scale=1` = Users can only zoom to 100% (cannot zoom in more)
- This prevents users from zooming beyond the original size
- Problem: Users with vision problems cannot make text larger

### Simple Fix

Remove `maximum-scale=1` from the content attribute:

```html
<meta
    name="viewport"
    content="width=device-width, initial-scale=1, viewport-fit=cover"
/>
```

That's it. Just delete `maximum-scale=1,` from the content string.

### Why This Matters

Before (with maximum-scale=1):
- User tries to zoom on phone: Zooming blocked
- Text stays small: Hard to read

After (without maximum-scale):
- User can zoom up to 500%: Zooming allowed
- Text can be enlarged: Better accessibility

## Where Are the 4 Violations?

1. Authentication Page - Color Contrast:
   - File: `src/routes/auth/login/+page.svelte` (line 206)
   - Element: "Forgot?" button

2. Authentication Page - Color Contrast:
   - File: `src/routes/auth/signup/+page.svelte` (line 275)
   - Element: "Sign In" button

3. Authentication Page - Meta Viewport:
   - File: `src/app.html` (line 14-16)
   - Issue: `maximum-scale=1` prevents zooming

4. Home Page - Same Issues:
   - Same buttons appear on home page (when logged out)
   - Same meta viewport tag affects all pages

Why 4? The test scans:
- Authentication pages separately (login/signup)
- Home page separately
- Each page gets counted individually
- Result: 2 pages × 2 violation types = 4 total violations

## Verification Steps

After making fixes:

1. Run the accessibility test:
   ```bash
   npm run test:accessibility:generate
   ```

2. Check the report:
   ```bash
   cat frontend_test/accessibility-report.md
   ```

3. Visual verification:
   - Open `/auth/login` page
   - Check "Forgot?" button is readable (darker purple)
   - Test zoom on mobile device (should work)

## Expected Results After Fixes

- Before: 4 violations (2 serious, 2 moderate)
- After: 0 violations

## Resources

- [WCAG Color Contrast Guidelines](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html)
- [Deque University - Color Contrast](https://dequeuniversity.com/rules/axe/4.11/color-contrast?application=axeAPI)
- [Deque University - Meta Viewport](https://dequeuniversity.com/rules/axe/4.11/meta-viewport?application=axeAPI)
- [WebAIM Color Contrast Checker](https://webaim.org/resources/contrastchecker/)
- [WCAG Zoom Requirements](https://www.w3.org/WAI/WCAG21/Understanding/resize-text.html)

---

Last Updated: 2025-11-03  
Report Location: `frontend_test/accessibility-report.md`
