export type ViolationKey =
  | 'min_length'
  | 'uppercase'
  | 'lowercase'
  | 'digit'
  | 'symbol'
  | 'contains_profile'
  | 'too_common'
  | 'too_weak'
  | 'too_long';

export const POLICY = {
  minLength: 10,
  maxLength: 128,
  requireUpper: true,
  requireLower: true,
  requireDigit: true,
  requireSymbol: true
};

const COMMON = new Set([
  'password','123456','qwerty','letmein','welcome','admin','iloveyou','111111',
  '123456789','abc123','123123','password1','cerebra','cerebraui'
]);

function normalize(s: string) {
  return (s || '').toLowerCase().replace(/\s+/g, '');
}

export function validatePassword(
  password: string,
  ctx?: { email?: string; name?: string; useZXCVBN?: boolean }
): { ok: boolean; violations: ViolationKey[] } {
  const v: ViolationKey[] = [];
  const pw = password ?? '';

  if (pw.length < POLICY.minLength) v.push('min_length');
  if (pw.length > POLICY.maxLength) v.push('too_long');
  if (POLICY.requireUpper && !/[A-Z]/.test(pw)) v.push('uppercase');
  if (POLICY.requireLower && !/[a-z]/.test(pw)) v.push('lowercase');
  if (POLICY.requireDigit && !/[0-9]/.test(pw)) v.push('digit');
  if (POLICY.requireSymbol && !/[^A-Za-z0-9]/.test(pw)) v.push('symbol');

  const name = normalize(ctx?.name || '');
  const email = normalize(ctx?.email || '');
  const emailLocal = email.split('@')[0] || '';
  if (name && pw.toLowerCase().includes(name)) v.push('contains_profile');
  if (emailLocal && pw.toLowerCase().includes(emailLocal)) v.push('contains_profile');

  if (COMMON.has(pw.toLowerCase())) v.push('too_common');

  // Optional: zxcvbn if available (no hard dependency)
  if (ctx?.useZXCVBN && typeof (globalThis as any).zxcvbn === 'function') {
    try {
      const score = (globalThis as any).zxcvbn(pw).score; // 0..4
      if (score < 3) v.push('too_weak');
    } catch {}
  }

  return { ok: v.length === 0, violations: v };
}

export const violationMessage: Record<ViolationKey, string> = {
  min_length: 'Use at least 10 characters.',
  uppercase: 'Add an uppercase letter (A–Z).',
  lowercase: 'Add a lowercase letter (a–z).',
  digit: 'Add a number (0–9).',
  symbol: 'Add a symbol (e.g., ! @ # ? ).',
  contains_profile: "Don't include your name or email.",
  too_common: 'This password is too common.',
  too_weak: 'Password is too weak; try a longer, less predictable phrase.',
  too_long: 'Use at most 128 characters.'
};