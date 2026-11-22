from copy import deepcopy

def _p(id, title, difficulty, topics, description, input_format, output_format, constraints, examples, starter, public, hidden):
    return {"id": id, "title": title, "difficulty": difficulty, "topics": topics, "description": description,
            "input_format": input_format, "output_format": output_format, "constraints": constraints,
            "examples": examples, "starter_code": starter, "public_tests": public, "hidden_tests": hidden}

PROBLEMS = [
_p("two-sum", "Two Sum", "Easy", ["Arrays", "Hashing"], "Find the two positions whose values add to the target.", "First line: integers. Second line: target.", "Print the two zero-based indices in increasing order.", ["2 <= n <= 10^4"], [("2 7 11 15\n9", "0 1"), ("3 2 4\n6", "1 2")], """class Solution:
    def twoSum(self, nums: List[int], target: int) -> List[int]:
        
""", [("2 7 11 15\n9", "0 1"), ("3 2 4\n6", "1 2")], [("3 3\n6", "0 1"), ("1 5 3 7\n10", "2 3")]),

_p("reverse-string", "Reverse a String", "Easy", ["Strings"], "Reverse the supplied line without changing its characters.", "One line containing a string.", "Print the reversed string.", ["The string length is at most 10^5."], [("arena", "anera"), ("hello", "olleh")], """class Solution:
    def reverseString(self, s: str) -> str:
        
""", [("arena", "anera"), ("hello", "olleh")], [("code", "edoc"), ("", "")]),

_p("valid-anagram", "Valid Anagram", "Easy", ["Hashing", "Strings"], "Decide whether the two input words contain exactly the same letters.", "Two whitespace-separated strings.", "Print True or False.", ["Inputs contain lowercase English letters."], [("listen silent", "True"), ("rat car", "False")], """class Solution:
    def isAnagram(self, s: str, t: str) -> bool:
        
""", [("listen silent", "True"), ("rat car", "False")], [("triangle integral", "True"), ("abc ab", "False")]),

_p("maximum-subarray", "Maximum Subarray", "Medium", ["Dynamic Programming"], "Find the largest sum of a non-empty contiguous slice.", "One line of integers.", "Print the maximum slice sum.", ["1 <= n <= 10^5"], [("-2 1 -3 4 -1 2 1 -5 4", "6"), ("5 4 -1 7 8", "23")], """class Solution:
    def maxSubArray(self, nums: List[int]) -> int:
        
""", [("-2 1 -3 4 -1 2 1 -5 4", "6"), ("5 4 -1 7 8", "23")], [("-5 -2 -8", "-2"), ("1", "1")]),

_p("stock-profit", "Best Time to Buy and Sell Stock", "Easy", ["Arrays"], "Choose one buy day and a later sell day to maximize profit.", "One line of daily prices.", "Print the maximum profit, or zero when no profit is possible.", ["Prices are non-negative."], [("7 1 5 3 6 4", "5"), ("7 6 4 3 1", "0")], """class Solution:
    def maxProfit(self, prices: List[int]) -> int:
        
""", [("7 1 5 3 6 4", "5"), ("7 6 4 3 1", "0")], [("2 4 1", "2"), ("3 3", "0")]),

_p("longest-substring", "Longest Substring Without Repeating Characters", "Medium", ["Sliding Window"], "Find the length of the longest contiguous substring with no repeated character.", "One line containing a string.", "Print its length.", ["The string may contain any visible ASCII characters."], [("abcabcbb", "3"), ("bbbbb", "1")], """class Solution:
    def lengthOfLongestSubstring(self, s: str) -> int:
        
""", [("abcabcbb", "3"), ("bbbbb", "1")], [("pwwkew", "3"), ("", "0")]),

_p("contains-duplicate", "Contains Duplicate", "Easy", ["Hashing"], "Determine whether any value occurs at least twice.", "One line of integers.", "Print True or False.", ["n is at least 1."], [("1 2 3 1", "True"), ("1 2 3 4", "False")], """class Solution:
    def containsDuplicate(self, nums: List[int]) -> bool:
        
""", [("1 2 3 1", "True"), ("1 2 3 4", "False")], [("9 9", "True"), ("5", "False")]),

_p("product-except-self", "Product of Array Except Self", "Medium", ["Arrays"], "For every position, print the product of all other values without division.", "One line of integers.", "Print the products separated by spaces.", ["Use O(n) time."], [("1 2 3 4", "24 12 8 6"), ("-1 1 0 -3 3", "0 0 9 0 0")], """class Solution:
    def productExceptSelf(self, nums: List[int]) -> List[int]:
        
""", [("1 2 3 4", "24 12 8 6"), ("-1 1 0 -3 3", "0 0 9 0 0")], [("2 3", "3 2"), ("0 4", "4 0")]),

_p("binary-search", "Binary Search", "Easy", ["Binary Search"], "Return the index of target in a sorted list, or -1 if absent.", "First line: sorted integers. Second line: target.", "Print the zero-based index.", ["The list is sorted in ascending order."], [("1 3 5 7 9\n7", "3"), ("1 3 5 7 9\n4", "-1")], """class Solution:
    def search(self, nums: List[int], target: int) -> int:
        
""", [("1 3 5 7 9\n7", "3"), ("1 3 5 7 9\n4", "-1")], [("2 4 6\n2", "0"), ("2 4 6\n8", "-1")]),

_p("valid-parentheses", "Valid Parentheses", "Easy", ["Stack"], "Check whether brackets are balanced and correctly nested.", "One line containing brackets.", "Print True or False.", ["Only (), [], and {} occur."], [("()[]{}", "True"), ("([)]", "False")], """class Solution:
    def isValid(self, s: str) -> bool:
        
""", [("()[]{}", "True"), ("([)]", "False")], [("{[()]} ", "True"), ("(", "False")]),

_p("merge-sorted-lists", "Merge Two Sorted Lists", "Easy", ["Linked Lists"], "Merge two sorted integer sequences into one sorted sequence.", "Two lines, one sorted sequence per line.", "Print the merged values separated by spaces.", ["Both sequences may be empty."], [("1 2 4\n1 3 4", "1 1 2 3 4 4"), ("\n0", "0")], """class Solution:
    def mergeTwoLists(self, list1: List[int], list2: List[int]) -> List[int]:
        
""", [("1 2 4\n1 3 4", "1 1 2 3 4 4"), ("\n0", "0")], [("2 5\n1 7", "1 2 5 7"), ("\n", "")]),

_p("climbing-stairs", "Climbing Stairs", "Easy", ["Dynamic Programming"], "Count the ways to reach stair n when each move is one or two stairs.", "One integer n.", "Print the number of ways.", ["1 <= n <= 45"], [("2", "2"), ("5", "8")], """class Solution:
    def climbStairs(self, n: int) -> int:
        
""", [("2", "2"), ("5", "8")], [("1", "1"), ("10", "89")]),
]

def public_problem(p):
    result = deepcopy(p)
    result.pop("hidden_tests", None)
    result.pop("public_tests", None)
    return result

def get_problem(problem_id):
    return next((p for p in PROBLEMS if p["id"] == problem_id), None)
