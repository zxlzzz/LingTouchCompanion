// 极简测试框架：不引入外部依赖，云端和本机都能直接编。
#pragma once

#include <cstdio>
#include <string>
#include <vector>

namespace lt_test {

struct Case {
  const char* name;
  void (*fn)();
};

inline std::vector<Case>& cases() {
  static std::vector<Case> c;
  return c;
}

inline int& failures() {
  static int f = 0;
  return f;
}

struct Registrar {
  Registrar(const char* name, void (*fn)()) { cases().push_back(Case{name, fn}); }
};

inline int run_all() {
  for (const Case& c : cases()) {
    const int before = failures();
    c.fn();
    std::printf("%s %s\n", failures() == before ? "PASS" : "FAIL", c.name);
  }
  std::printf("%zu case(s), %d failed check(s)\n", cases().size(), failures());
  return failures() == 0 ? 0 : 1;
}

}  // namespace lt_test

#define LT_TEST(name)                                          \
  static void name();                                          \
  static const lt_test::Registrar name##_registrar(#name, name); \
  static void name()

#define LT_CHECK(cond)                                                              \
  do {                                                                              \
    if (!(cond)) {                                                                  \
      std::printf("  %s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond);        \
      ++lt_test::failures();                                                        \
    }                                                                               \
  } while (0)

#define LT_CHECK_MSG(cond, msg)                                                                   \
  do {                                                                                            \
    if (!(cond)) {                                                                                \
      std::printf("  %s:%d: CHECK failed: %s (%s)\n", __FILE__, __LINE__, #cond, std::string(msg).c_str()); \
      ++lt_test::failures();                                                                      \
    }                                                                                             \
  } while (0)

#define LT_CHECK_NEAR(a, b, tol)                                                                          \
  do {                                                                                                    \
    const double lt_a_ = (a), lt_b_ = (b);                                                                \
    if (!(lt_a_ - lt_b_ <= (tol) && lt_b_ - lt_a_ <= (tol))) {                                            \
      std::printf("  %s:%d: CHECK_NEAR failed: %s = %.9g, %s = %.9g\n", __FILE__, __LINE__, #a, lt_a_, #b, \
                  lt_b_);                                                                                 \
      ++lt_test::failures();                                                                              \
    }                                                                                                     \
  } while (0)

#define LT_TEST_MAIN() \
  int main() { return lt_test::run_all(); }
