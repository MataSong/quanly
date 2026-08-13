export interface PasswordRules {
  minLen: boolean;
  upper: boolean;
  lower: boolean;
  digit: boolean;
  special: boolean;
  valid: boolean;
}

export interface PasswordScore {
  score: 0 | 1 | 2 | 3 | 4;
  level: "weak" | "medium" | "strong";
}

export function checkRules(pw: string): PasswordRules {
  const minLen = pw.length >= 8;
  const upper = /[A-Z]/.test(pw);
  const lower = /[a-z]/.test(pw);
  const digit = /[0-9]/.test(pw);
  const special = /[^A-Za-z0-9]/.test(pw);
  const categoryCount = [upper, lower, digit, special].filter(Boolean).length;
  const valid = minLen && categoryCount >= 3;
  return { minLen, upper, lower, digit, special, valid };
}

export function scorePassword(pw: string): PasswordScore {
  const rules = checkRules(pw);
  const categoryCount = [rules.upper, rules.lower, rules.digit, rules.special].filter(Boolean).length;

  let score: 0 | 1 | 2 | 3 | 4 = 0;
  if (pw.length === 0) {
    score = 0;
  } else if (!rules.minLen || categoryCount < 2) {
    score = 1;
  } else if (categoryCount === 2 || (categoryCount === 3 && pw.length < 12)) {
    score = 2;
  } else if (categoryCount >= 3 && pw.length >= 8) {
    score = 3;
  }
  if (categoryCount >= 4 && pw.length >= 12) score = 4;

  let level: "weak" | "medium" | "strong";
  if (score <= 1) level = "weak";
  else if (score === 2) level = "medium";
  else level = "strong";

  return { score, level };
}
