/* COVERAGE=1 (run/test_menu.sh): the runner leaves through _exit(), which skips the
   atexit hook that writes the LLVM profile.  The coverage build compiles runner.cpp with
   -D_exit=cov_exit, so every _exit writes the profile first. */
#include <unistd.h>

int __llvm_profile_write_file(void);

void cov_exit(int code) {
  __llvm_profile_write_file();
  _exit(code);
}
