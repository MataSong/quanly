export interface PasswordRule {
  key: string; // i18n 文案 key
  passed: boolean;
}

// 规则(与后端 RegisterSerializer 校验保持一致):至少 8 位、含字母、含数字
export function checkPassword(pwd: string): PasswordRule[] {
  return [
    { key: "password.rule.len", passed: pwd.length >= 8 },
    { key: "password.rule.letter", passed: /[A-Za-z]/.test(pwd) },
    { key: "password.rule.digit", passed: /\d/.test(pwd) },
  ];
}

export function isPasswordValid(pwd: string): boolean {
  return checkPassword(pwd).every((r) => r.passed);
}

// 强度 0-3:满足的规则数;额外长度加成
export function passwordStrength(pwd: string): number {
  if (!pwd) return 0;
  const passed = checkPassword(pwd).filter((r) => r.passed).length;
  const bonus = pwd.length >= 12 ? 1 : 0;
  return Math.min(passed + bonus, 3);
}
