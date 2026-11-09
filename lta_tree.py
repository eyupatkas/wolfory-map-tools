"""Read LithTech ASCII node trees and preserve source spans."""
import re
from dataclasses import dataclass

TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+')

@dataclass
class Node:
    start: int
    end: int
    items: list
    @property
    def head(self):
        return self.items[0] if self.items and isinstance(self.items[0], str) else None

def parse(text):
    roots, stack = [], []
    for m in TOKEN.finditer(text):
        value = m[0]
        if value == '(':
            n = Node(m.start(), -1, [])
            (stack[-1].items if stack else roots).append(n)
            stack.append(n)
        elif value == ')':
            if not stack:
                raise ValueError('Unbalanced LTA')
            stack.pop().end = m.end()
        elif stack:
            stack[-1].items.append(value)
        else:
            raise ValueError('Unexpected LTA atom')
    if stack:
        raise ValueError('Unbalanced LTA')
    return Node(0, len(text), roots)

def children(n):
    v = n.items[1:] if n.head else n.items
    return v[0].items if len(v) == 1 and isinstance(v[0], Node) and v[0].head is None else v

def named(n, key):
    return next(v for v in children(n) if isinstance(v, Node) and v.head == key)

def walk(n):
    yield n
    for v in n.items:
        if isinstance(v, Node):
            yield from walk(v)

def raw(text, n):
    return text[n.start:n.end]
