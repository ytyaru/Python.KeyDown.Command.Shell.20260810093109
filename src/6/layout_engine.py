#!/usr/bin/env python3
import unicodedata

KEYS = "0123456789abcdefghijklmnopqrstuvwxyz"

def get_display_width(text):
    """全角文字・東アジアの曖昧な文字(Ambiguous)を2、半角文字を1として実際の表示幅を計算する"""
    width = 0
    for ch in str(text):
        status = unicodedata.east_asian_width(ch)
        if status in ('F', 'W', 'A'):
            width += 2
        else:
            width += 1
    return width

class LayoutEngine:
    """全ページの動的ページサイズと絶対インデックスを管理する（単一責任：数理ロジック）"""
    def __init__(self, all_items, term_cols, term_lines):
        self.all_items = all_items
        self.page_starts = [0]  # 構文修正: 初期値 0 を含むリストとして正しく初期化
        self.page_layouts = []  # 各ページの (cols, rows, size) を保持
        
        current_idx = 0
        total_items = len(all_items)
        
        reserved_lines = 3
        max_rows = max(1, term_lines - reserved_lines)
        
        while current_idx < total_items:
            rem_items = all_items[current_idx:]
            
            best_c = 1
            best_r = min(max_rows, len(rem_items))
            best_size = best_r
            
            if len(rem_items) <= max_rows:
                best_c = 1
                best_r = len(rem_items)
                best_size = len(rem_items)
            else:
                for c in range(1, len(KEYS) + 1):
                    t_rows = min(max_rows, (len(rem_items) + c - 1) // c)
                    t_size = min(len(KEYS), c * t_rows)
                    p_items = rem_items[:t_size]
                    if not p_items:
                        break
                        
                    needed_width = 0
                    for i in range(c):
                        col_items = p_items[i * t_rows : (i + 1) * t_rows]
                        if col_items:
                            max_w = max(get_display_width(x) for x in col_items)
                            needed_width += max_w + 5
                    
                    if needed_width <= term_cols and t_size <= len(KEYS):
                        best_c, best_r, best_size = c, t_rows, t_size
                    else:
                        break
            
            self.page_layouts.append((best_c, best_r, best_size))
            current_idx += best_size
            
            if current_idx < total_items:
                self.page_starts.append(current_idx)
                
        self.total_pages = len(self.page_layouts)

    def get_page_info(self, page_num):
        if page_num >= self.total_pages:
            page_num = 0
        return self.page_starts[page_num], self.page_layouts[page_num]
