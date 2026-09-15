import pandas as pd
import re
import json
import os
import unicodedata
from underthesea import pos_tag

class TrieNode:
    def __init__(self):
        self.children = {}
        self.is_end = False
        self.canonical_text = None
        self.required_case = None # Original phrase if case-sensitive match is required

class VnTokenizer:
    def __init__(self, csv_path, finger_spell_names=True):
        """
        Custom Vietnamese Tokenizer for sign language dictionary data.
        
        Priority Logic:
        1. Exact Match Priority (3 levels: Original > Core/Outside > Inside Parens)
        2. Selective Case Sensitivity:
           - Capitalized keys (e.g., 'Anh') require EXACT casing.
           - Lowercase keys (e.g., 'hoa') match case-insensitively.
        3. Gap processing with POS-targeted bit-splitting (Np only).
        """
        self.root = TrieNode()
        self.csv_path = csv_path
        self.finger_spell_names = finger_spell_names
        self.valid_canonicals = set()
        
        # Blacklist of non-essential words
        self.blacklist = {"là", "thì", "mà", "và", "của", "rằng", "thế", "này", "cũng"}
        
        # Common Vietnamese classifiers to strip for Level 2 core nouns
        self.classifiers = {
            "con", "cái", "chiếc", "tấm", "bức", "ngôi", "quyển", "tờ", "bản", 
            "vị", "viên", "hạt", "bóng", "cây", "sợi", "hòn", "khúc", "người"
        }
        
        self._load_dictionary()

    def _split_to_words(self, text):
        """Consistent word/punctuation splitting. Preserves case for POS tagging."""
        return re.findall(r'[\w-]+|[^\w\s]', text, re.UNICODE)

    def _load_dictionary(self):
        try:
            df = pd.read_csv(self.csv_path)
        except Exception as e:
            print(f"Error loading CSV: {e}")
            return

        def select_variant(group):
            b_variant = group[group['image_id'].str.endswith('B', na=False)]
            if not b_variant.empty:
                return b_variant.iloc[0]
            non_variant = group[~group['image_id'].str.contains(r'[BNT]$', na=False, regex=True)]
            if not non_variant.empty:
                return non_variant.iloc[0]
            return None

        unique_entries = df.groupby('text', group_keys=False).apply(select_variant).dropna()

        # 3 Levels of Priority
        p1 = {} 
        p2 = {} 
        p3 = {} 

        def add_to_p_map(p_map, key, canonical):
            if not key: return
            k_lower = key.strip().lower()
            # If the original key has uppercase, mark it for case-sensitivity
            p_map[k_lower] = (canonical, key.strip() if any(c.isupper() for c in key) else None)

        def strip_classifier(phrase):
            words = phrase.split()
            if len(words) > 1 and words[0].lower() in self.classifiers:
                return " ".join(words[1:])
            return None

        # Pass 1: Categorize all entries
        for phrase_index, row in unique_entries.iterrows():
            phrase = str(phrase_index)
            
            # Quoted synonyms -> P1
            if phrase.startswith('"') and phrase.endswith('"'):
                synonyms = phrase[1:-1].split(',')
                for s in synonyms:
                    add_to_p_map(p1, s, phrase)
                continue

            # Original Phrases (no parens) -> P1
            if '(' not in phrase:
                add_to_p_map(p1, phrase, phrase)
                # Classifier stripped -> P2
                core = strip_classifier(phrase)
                if core: add_to_p_map(p2, core, phrase)
            else:
                # Text outside parens -> P2
                clean_phrase = re.sub(r'\(.*?\)', '', phrase).strip()
                if clean_phrase:
                    add_to_p_map(p2, clean_phrase, phrase)
                
                # Text inside parens -> P3
                parens = re.findall(r'\((.*?)\)', phrase)
                if len(parens) == 1:
                    inside = parens[0].strip()
                    # Strip prefixes like "nước ", "tỉnh ", "giống: ", "như: ", etc.
                    clean_inside = re.sub(r'^(nước|tỉnh|thành phố|huyện|xã|giống:|như:)\s+', '', inside, flags=re.IGNORECASE)
                    add_to_p_map(p3, clean_inside, phrase)

            # Holiday logic -> P3
            date_match = re.search(r'^ngày\s+(.*?)\s+\d+/\d+', phrase, re.IGNORECASE)
            if date_match:
                core_holiday = date_match.group(1).strip()
                add_to_p_map(p3, core_holiday, phrase)

        # Build Trie: Add in reverse priority order (Low -> High)
        for p_map in [p3, p2, p1]:
            for key_lower, (canonical, req_case) in p_map.items():
                self._add_to_trie(key_lower, canonical, req_case)

        # Manual overrides (P1 equivalent)
        self.add_alias("8/3", "ngày Quốc tế phụ nữ 8/3")
        self.add_alias("quốc tế phụ nữ", "ngày Quốc tế phụ nữ 8/3")

    def _add_to_trie(self, phrase_lower, canonical, required_case=None):
        words = self._split_to_words(phrase_lower)
        if not words: return
        
        node = self.root
        for word in words:
            if word not in node.children:
                node.children[word] = TrieNode()
            node = node.children[word]
        node.is_end = True
        node.canonical_text = canonical
        node.required_case = required_case
        self.valid_canonicals.add(phrase_lower)

    def add_alias(self, alias, target_canonical):
        """Manually add an alias with Priority 1."""
        a_lower = alias.strip().lower()
        # Aliases are generally case-insensitive unless they contain uppercase
        req_case = alias.strip() if any(c.isupper() for c in alias) else None
        self._add_to_trie(a_lower, target_canonical, req_case)

    def _normalize_name(self, name):
        """Removes diacritics and tone marks for clean finger-spelling."""
        # Special case for Vietnamese 'đ'
        name = name.replace('đ', 'd').replace('Đ', 'D')
        nfkd_form = unicodedata.normalize('NFKD', name)
        # Keep only basic alphanumeric characters
        return "".join([c for c in nfkd_form if not unicodedata.combining(c) and c.isalnum()])

    def tokenize(self, sentence):
        """
        Tokenizes the sentence using a hybrid approach:
        1. Dictionary Trie matching (Longest Match First, weighted by Priority).
        2. Context-aware POS tagging for gaps (to handle Proper Nouns via finger-spelling).
        """
        # 1. Full-sentence POS tagging for context-aware Np detection
        try:
            full_pos = pos_tag(sentence)
        except:
            full_pos = []
            
        # Create a tag map: character index -> tag
        char_to_tag = {}
        curr_idx = 0
        for segment, tag in full_pos:
            start_pos = sentence.find(segment, curr_idx)
            if start_pos != -1:
                for i in range(start_pos, start_pos + len(segment)):
                    char_to_tag[i] = tag
                curr_idx = start_pos + len(segment)

        words = self._split_to_words(sentence)
        n = len(words)
        result_tokens = []
        
        # Track word start positions in the original sentence for tag lookup
        word_spans = []
        curr_p = 0
        for w in words:
            sp = sentence.find(w, curr_p)
            word_spans.append((sp, sp + len(w)))
            curr_p = sp + len(w)

        i = 0
        while i < n:
            match_canonical = None
            match_len = 0
            
            node = self.root
            for j in range(i, n):
                word_lower = words[j].lower()
                if word_lower in node.children:
                    node = node.children[word_lower]
                    if node.is_end:
                        # Case Sensitivity Check
                        if node.required_case:
                            current_segment = " ".join(words[i:j+1])
                            if current_segment == node.required_case:
                                match_canonical = node.canonical_text
                                match_len = j - i + 1
                        else:
                            match_canonical = node.canonical_text
                            match_len = j - i + 1
                else:
                    break
            
            if match_canonical:
                result_tokens.append(match_canonical)
                i += match_len
            else:
                # Gap processing
                gap_start = i
                # Advance i until the next dictionary match or end of string
                while i < n:
                    is_match_start = False
                    temp_node = self.root
                    for k in range(i, n):
                        w_l = words[k].lower()
                        if w_l in temp_node.children:
                            temp_node = temp_node.children[w_l]
                            if temp_node.is_end:
                                # Consider casing
                                if not temp_node.required_case or " ".join(words[i:k+1]) == temp_node.required_case:
                                    is_match_start = True
                                    break
                        else:
                            break
                    if is_match_start: break
                    i += 1
                
                # Process the gap words using pre-calculated tags
                for k in range(gap_start, i):
                    word_form = words[k]
                    wf_lower = word_form.lower()
                    
                    # Determine tag from char_to_tag
                    start, end = word_spans[k]
                    tag = char_to_tag.get(start + (end - start)//2, 'None')
                    
                    # Heuristic for Names (Proper Nouns):
                    # 1. Tagged as Np by context
                    # 2. Capitalized AND not a dictionary word (e.g., "Duy" vs "duy")
                    is_prop_noun = (tag == 'Np' or 
                                   (word_form[0].isupper() and wf_lower not in self.valid_canonicals))
                    
                    if wf_lower in self.blacklist:
                        continue
                    if re.match(r'[^\w\s]', word_form) and wf_lower not in self.valid_canonicals:
                        continue

                    if self.finger_spell_names and is_prop_noun:
                        # Normalize name (remove diacritics) before finger-spelling
                        normalized = self._normalize_name(word_form)
                        result_tokens.extend(list(normalized))
                    else:
                        result_tokens.append(word_form)
        
        return result_tokens

if __name__ == "__main__":
    CSV_PATH = "dictionary_data.csv"
    if not os.path.exists(CSV_PATH):
        print(f"Error: {CSV_PATH} not found.")
    else:
        print("Loading dictionary... please wait.")
        tokenizer = VnTokenizer(CSV_PATH)
        
        print("\n=== Vietnamese Sign Language Tokenizer ===")
        print("Selective Case: Proper Nouns (capitalized) require exact case.")
        print("Proper nouns (Np) will be finger-spelled.")
        print("Type 'exit' to quit.")
        
        try:
            while True:
                sentence = input("\nInput: ")
                if sentence.lower() in ['exit', 'quit']:
                    print("Goodbye!")
                    break
                if not sentence.strip():
                    continue
                    
                tokens = tokenizer.tokenize(sentence)
                print(f"Tokens: {tokens}")
        except KeyboardInterrupt:
            print("\nGoodbye!")
