"""
CodeArena Harness & Driver Generator.
Automatically wraps student class-based solutions with imports and I/O drivers.
"""

HEADER_IMPORTS = """import sys, math, collections, itertools, functools, heapq
from typing import List, Dict, Set, Optional, Tuple, Any, Union
"""

DRIVERS = {
    "two-sum": """
if __name__ == "__main__":
    _raw = sys.stdin.read().replace('\\\\n', '\\n').strip()
    _lines = [l.strip() for l in _raw.splitlines() if l.strip()]
    if len(_lines) >= 2:
        _nums = [int(x) for x in _lines[0].split()]
        _target = int(_lines[1].split()[0])
    elif len(_lines) == 1:
        _toks = [int(x) for x in _lines[0].split()]
        _nums = _toks[:-1]
        _target = _toks[-1]
    else:
        _nums, _target = [], 0
    _sol = Solution()
    _fn = getattr(_sol, "twoSum", None) or getattr(_sol, "two_sum", None) or getattr(_sol, "solve", None)
    _res = _fn(_nums, _target)
    if isinstance(_res, (list, tuple)):
        print(" ".join(str(x) for x in sorted(_res)))
    else:
        print(_res)
""",
    "reverse-string": """
if __name__ == "__main__":
    _s = sys.stdin.read().replace('\\\\n', '\\n').rstrip("\\r\\n")
    _sol = Solution()
    _fn = getattr(_sol, "reverseString", None) or getattr(_sol, "reverse_string", None) or getattr(_sol, "solve", None)
    if _fn:
        _res = _fn(_s)
        print(_res if _res is not None else "")
""",
    "valid-anagram": """
if __name__ == "__main__":
    _parts = sys.stdin.read().replace('\\\\n', '\\n').split()
    if len(_parts) >= 2:
        _sol = Solution()
        _fn = getattr(_sol, "isAnagram", None) or getattr(_sol, "is_anagram", None) or getattr(_sol, "solve", None)
        print(bool(_fn(_parts[0], _parts[1])))
""",
    "maximum-subarray": """
if __name__ == "__main__":
    _raw = sys.stdin.read().replace('\\\\n', '\\n').split()
    if _raw:
        _nums = [int(_x) for _x in _raw]
        _sol = Solution()
        _fn = getattr(_sol, "maxSubArray", None) or getattr(_sol, "max_sub_array", None) or getattr(_sol, "solve", None)
        print(_fn(_nums))
""",
    "stock-profit": """
if __name__ == "__main__":
    _raw = sys.stdin.read().replace('\\\\n', '\\n').split()
    if _raw:
        _prices = [int(_x) for _x in _raw]
        _sol = Solution()
        _fn = getattr(_sol, "maxProfit", None) or getattr(_sol, "max_profit", None) or getattr(_sol, "solve", None)
        print(_fn(_prices))
""",
    "longest-substring": """
if __name__ == "__main__":
    _s = sys.stdin.read().replace('\\\\n', '\\n').rstrip("\\r\\n")
    _sol = Solution()
    _fn = getattr(_sol, "lengthOfLongestSubstring", None) or getattr(_sol, "length_of_longest_substring", None) or getattr(_sol, "solve", None)
    print(_fn(_s))
""",
    "contains-duplicate": """
if __name__ == "__main__":
    _raw = sys.stdin.read().replace('\\\\n', '\\n').split()
    if _raw:
        _nums = [int(_x) for _x in _raw]
        _sol = Solution()
        _fn = getattr(_sol, "containsDuplicate", None) or getattr(_sol, "contains_duplicate", None) or getattr(_sol, "solve", None)
        print(bool(_fn(_nums)))
""",
    "product-except-self": """
if __name__ == "__main__":
    _raw = sys.stdin.read().replace('\\\\n', '\\n').split()
    if _raw:
        _nums = [int(_x) for _x in _raw]
        _sol = Solution()
        _fn = getattr(_sol, "productExceptSelf", None) or getattr(_sol, "product_except_self", None) or getattr(_sol, "solve", None)
        _res = _fn(_nums)
        if isinstance(_res, (list, tuple)):
            print(" ".join(str(_x) for _x in _res))
        else:
            print(_res)
""",
    "binary-search": """
if __name__ == "__main__":
    _raw = sys.stdin.read().replace('\\\\n', '\\n').strip()
    _lines = [l.strip() for l in _raw.splitlines() if l.strip()]
    if len(_lines) >= 2:
        _nums = [int(_x) for _x in _lines[0].split()]
        _target = int(_lines[1].split()[0])
        _sol = Solution()
        _fn = getattr(_sol, "search", None) or getattr(_sol, "binarySearch", None) or getattr(_sol, "solve", None)
        print(_fn(_nums, _target))
""",
    "valid-parentheses": """
if __name__ == "__main__":
    _s = sys.stdin.read().replace('\\\\n', '\\n').strip()
    _sol = Solution()
    _fn = getattr(_sol, "isValid", None) or getattr(_sol, "is_valid", None) or getattr(_sol, "solve", None)
    print(bool(_fn(_s)))
""",
    "merge-sorted-lists": """
if __name__ == "__main__":
    _raw = sys.stdin.read().replace('\\\\n', '\\n')
    _lines = _raw.splitlines()
    _l1 = [int(_x) for _x in _lines[0].split()] if len(_lines) > 0 and _lines[0].strip() else []
    _l2 = [int(_x) for _x in _lines[1].split()] if len(_lines) > 1 and _lines[1].strip() else []
    _sol = Solution()
    _fn = getattr(_sol, "mergeTwoLists", None) or getattr(_sol, "merge", None) or getattr(_sol, "solve", None)
    _res = _fn(_l1, _l2)
    if isinstance(_res, (list, tuple)):
        print(" ".join(str(_x) for _x in _res))
    else:
        print(_res if _res is not None else "")
""",
    "climbing-stairs": """
if __name__ == "__main__":
    _raw = sys.stdin.read().replace('\\\\n', '\\n').strip()
    if _raw:
        _n = int(_raw.split()[0])
        _sol = Solution()
        _fn = getattr(_sol, "climbStairs", None) or getattr(_sol, "climb_stairs", None) or getattr(_sol, "solve", None)
        print(_fn(_n))
""",
}

def prepare_code(problem_id: str, raw_code: str) -> str:
    """
    If the student submitted a `class Solution` without driver code,
    inject typing imports and problem-specific test driver harness.
    """
    code = raw_code.strip()
    
    # Prepend common imports (sys, typing, math, collections, etc.)
    prefix = HEADER_IMPORTS + "\n"
        
    # Check if student wrote a Solution class
    if "class Solution" in code and "__main__" not in code:
        driver = DRIVERS.get(problem_id, "")
        return f"{prefix}{code}\n{driver}"
        
    return f"{prefix}{code}"
