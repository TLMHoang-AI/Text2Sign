import pandas as pd
import re
import json
import os
from underthesea import word_tokenize

class TrieNode:
    def __init__(self):
        self.children = {}
        self.is_end = False
        self.canonical_text = None

class VnTokenizer:
    def __init__(self, csv_path, filter_unknown=True):
        """
        Custom Vietnamese Tokenizer for sign language dictionary data.
        Prioritizes exact matches from dictionary_data.csv using a Trie.
        Uses underthesea for gaps between dictionary matches.
        
        Args:
            csv_path (str): Path to dictionary_data.csv.
            filter_unknown (bool): If True, discard any tokens not in the dictionary (stopwords).
        """
        self.root = TrieNode()
        self.csv_path = csv_path
        self.filter_unknown = filter_unknown
        self.valid_canonicals = set()
        self._load_dictionary()

    def _split_to_words(self, text):
        """Consistent word/punctuation splitting for Trie and Tokenization."""
        return re.findall(r'[\w-]+|[^\w\s]', text.lower(), re.UNICODE)

    def _load_dictionary(self):
        try:
            df = pd.read_csv(self.csv_path)
        except Exception as e:
            print(f"Error loading CSV: {e}")
            return

        # Suffix B prioritization
        def select_variant(group):
            b_variant = group[group['image_id'].str.endswith('B', na=False)]
            if not b_variant.empty:
                return b_variant.iloc[0]
            non_variant = group[~group['image_id'].str.contains(r'[BNT]$', na=False, regex=True)]
            if not non_variant.empty:
                return non_variant.iloc[0]
            return None

        # Fixed Pandas compatibility and filtering
        unique_entries = df.groupby('text', group_keys=False).apply(select_variant).dropna()

        for phrase_index, row in unique_entries.iterrows():
            phrase = str(phrase_index)
            canonical = phrase
            self.valid_canonicals.add(canonical.lower())
            
            # 1. Quoted synonyms
            if phrase.startswith('"') and phrase.endswith('"'):
                synonyms = phrase[1:-1].split(',')
                for s in synonyms:
                    s_clean = s.strip()
                    self._add_to_trie(s_clean, canonical)
                    self.valid_canonicals.add(s_clean.lower())
                continue

            parens = re.findall(r'\((.*?)\)', phrase)

            # Rule: 2+ sets of () -> Ignore per user request
            if len(parens) >= 2:
                continue
            
            # 2. Rule: 1 or 0 sets of ()
            clean_phrase = re.sub(r'\(.*?\)', '', phrase).strip()
            if clean_phrase:
                self._add_to_trie(clean_phrase, canonical)
                self.valid_canonicals.add(clean_phrase.lower())
            
            # Add content inside parentheses (e.g., "Mi-an-ma", "nước Bra-xin")
            if len(parens) == 1:
                inside = parens[0].strip()
                self._add_to_trie(inside, canonical)
                self.valid_canonicals.add(inside.lower())
                # Handle "nước Bra-xin" -> trigger on "Bra-xin"
                core_name = re.sub(r'^(nước|tỉnh|thành phố|huyện|xã)\s+', '', inside, flags=re.IGNORECASE)
                if core_name != inside:
                    self._add_to_trie(core_name, canonical)
                    self.valid_canonicals.add(core_name.lower())
            
            # 3. Smart holiday/date triggers
            date_match = re.search(r'^ngày\s+(.*?)\s+\d+/\d+', phrase, re.IGNORECASE)
            if date_match:
                core_holiday = date_match.group(1).strip()
                self._add_to_trie(core_holiday, canonical)
                self.valid_canonicals.add(core_holiday.lower())

    def _add_to_trie(self, phrase, canonical):
        words = self._split_to_words(phrase)
        if not words:
            return
        
        node = self.root
        for word in words:
            if word not in node.children:
                node.children[word] = TrieNode()
            node = node.children[word]
        node.is_end = True
        node.canonical_text = canonical

    def add_alias(self, alias, target_canonical):
        """Manually add an alias for a specific dictionary entry."""
        self._add_to_trie(alias, target_canonical)
        self.valid_canonicals.add(alias.lower())
        self.valid_canonicals.add(target_canonical.lower())

    def tokenize(self, sentence):
        words = self._split_to_words(sentence)
        n = len(words)
        result_tokens = []
        i = 0
        
        while i < n:
            match_canonical = None
            match_len = 0
            
            node = self.root
            for j in range(i, n):
                word = words[j]
                if word in node.children:
                    node = node.children[word]
                    if node.is_end:
                        match_canonical = node.canonical_text
                        match_len = j - i + 1
                else:
                    break
            
            if match_canonical:
                result_tokens.append(match_canonical)
                i += match_len
            else:
                gap_start = i
                while i < n:
                    is_match_start = False
                    temp_node = self.root
                    for k in range(i, n):
                        if words[k] in temp_node.children:
                            temp_node = temp_node.children[words[k]]
                            if temp_node.is_end:
                                is_match_start = True
                                break
                        else:
                            break
                    if is_match_start: break
                    i += 1
                
                gap_text = " ".join(words[gap_start:i])
                if gap_text.strip():
                    underthesea_tokens = word_tokenize(gap_text)
                    if self.filter_unknown:
                        filtered = [t for t in underthesea_tokens if t.lower() in self.valid_canonicals]
                        result_tokens.extend(filtered)
                    else:
                        result_tokens.extend(underthesea_tokens)
        
        return result_tokens

if __name__ == "__main__":
    CSV_PATH = "dictionary_data.csv"
    if not os.path.exists(CSV_PATH):
        print(f"Error: {CSV_PATH} not found.")
    else:
        print("Loading dictionary... (filter_unknown=True)")
        tokenizer = VnTokenizer(CSV_PATH, filter_unknown=True)
        # Standardize triggers for holidays
        tokenizer.add_alias("8/3", "ngày Quốc tế phụ nữ 8/3")
        tokenizer.add_alias("quốc tế phụ nữ", "ngày Quốc tế phụ nữ 8/3")
        
        print("\n=== Vietnamese Sign Language Tokenizer ===")
        print("Words NOT in dictionary will be removed (Stopwords).")
        print("Type your sentence below to test. Type 'exit' to quit.")
        
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
