"""Small numeric gate with a negative control and measured residual."""
import sys


class Gates:
    def __init__(self):
        self.rows = []

    def numeric(self, name, observed, expected, falsified, tolerance=0.0):
        residual = abs(observed - expected)
        false_residual = abs(falsified - expected)
        ok = residual <= tolerance and false_residual > tolerance
        self.rows.append(ok)
        print("%s %s residual=%g tolerance=%g negative_residual=%g" %
              (name, "PASS" if ok else "FAIL", residual, tolerance, false_residual))
        return ok

    def finish(self):
        count = len(self.rows)
        passed = sum(self.rows)
        failed = count - passed
        print("checked %d gates, %d PASS, %d FAIL" % (count, passed, failed))
        return 0 if count and failed == 0 else 1


if __name__ == "__main__":
    print("This module is a helper; call Gates from a task-specific script.")
    sys.exit(2)

