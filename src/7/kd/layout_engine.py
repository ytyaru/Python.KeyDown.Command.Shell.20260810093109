#!/usr/bin/env python3

KEYS = "0123456789abcdefghijklmnopqrstuvwxyz"

class LayoutEngine:
    """ページ毎・列毎の最適化数理ロジック（単一責任：レイアウト計算）"""
    def __init__(self, all_items, page, term_cols, term_lines, total_pages_guess=1):
        self.all_items = all_items
        self.page = page
        
        reserved_lines = 3 if total_pages_guess > 1 else 2
        self.max_rows = max(1, term_lines - reserved_lines)
        self.max_page_size = min(len(KEYS), term_cols) 
        
        self.cols = 1
        self.rows = min(self.max_rows, len(all_items))
        self.page_size = self.rows
        
        for c in range(1, len(KEYS) + 1):
            test_rows = min(self.max_rows, (len(all_items) + c - 1) // c)
            test_size = min(len(KEYS), c * test_rows)
            
            start_idx = page * test_size
            page_items = all_items[start_idx:start_idx + test_size]
            if not page_items:
                break
                
            needed_width = 0
            for col_idx in range(c):
                col_items = page_items[col_idx * test_rows : (col_idx + 1) * test_rows]
                if col_items:
                    max_len = max(len(str(x)) for x in col_items)
                    needed_width += max_len + 5
                    
            if needed_width <= term_cols and test_size <= len(KEYS):
                self.cols = c
                self.rows = test_rows
                self.page_size = test_size
            else:
                break

        self.total_pages = (len(all_items) + self.page_size - 1) // self.page_size if all_items else 1

