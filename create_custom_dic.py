import pandas as pd
import re
import json

def create_filtered_dictionary(csv_path, output_csv="dictionary_data_B.csv", output_json="custom_dictionary.json"):
    """
    Refined dictionary creation based on user testing:
    1. Keeps only 'B' variants (or singles).
    2. Maps phrases inside parentheses (like 'Mi-an-ma' or 'Bra-xin') to canonical entries.
    3. Aggressively maps sub-phrases
    """
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    # Suffix B prioritization logic
    def select_row(group):
        b_variant = group[group['image_id'].str.endswith('B', na=False)]
        if not b_variant.empty:
            return b_variant.iloc[0]
        non_variant = group[~group['image_id'].str.contains(r'[BNT]$', na=False, regex=True)]
        if not non_variant.empty:
            return non_variant.iloc[0]
        return None

    # Fixed Pandas compatibility
    df_filtered = df.groupby('text', group_keys=False).apply(select_row).dropna()
    
    # Save the cleaned CSV
    df_filtered.to_csv(output_csv, index=True)
    print(f"Saved filtered dictionary to {output_csv}")

    custom_map = {}

    for text_entry, row in df_filtered.iterrows():
        original_phrase = str(text_entry)
        canonical = original_phrase
        
        # 1. Handle quoted synonyms (usually have 0 parens)
        if original_phrase.startswith('"') and original_phrase.endswith('"'):
            synonyms = original_phrase[1:-1].split(',')
            for s in synonyms:
                add_to_map(s, canonical)
            continue

        # Extract all content inside parentheses
        parens = re.findall(r'\((.*?)\)', original_phrase)

        # Rule: 2 or more sets of () -> Skip entirely per user request
        if len(parens) >= 2:
            continue
        
        # Rule: No parentheses or 1 set of ()
        clean_phrase = re.sub(r'\(.*?\)', '', original_phrase).strip()
        if clean_phrase:
            add_to_map(clean_phrase, canonical)
                
        # Handle the inside of parentheses (e.g., "Mi-an-ma", "nước Bra-xin")
        if len(parens) == 1:
            inside = parens[0].strip()
            add_to_map(inside, canonical)
            # If it contains "nước ", "tỉnh ", etc., also map the name only
            core_name = re.sub(r'^(nước|tỉnh|huyện|xã|thành phố)\s+', '', inside, flags=re.IGNORECASE)
            if core_name != inside:
                add_to_map(core_name, canonical)

        # 3. Handle specific holiday/event core phrases
        date_pattern = re.search(r'^ngày\s+(.*?)\s+\d+/\d+', original_phrase, re.IGNORECASE)
        if date_pattern:
            core_holiday = date_pattern.group(1).strip()
            add_to_map(core_holiday, canonical)

    # 4. Add manual aliases
    manual_aliases = {
        "8/3": "ngày Quốc tế phụ nữ 8/3",
        "30/4": "ngày Giải phóng miền Nam 30/4",
        "quốc tế phụ nữ": "ngày Quốc tế phụ nữ 8/3"
    }
    for alias, target in manual_aliases.items():
        add_to_map(alias, target)

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(custom_map, f, ensure_ascii=False, indent=4)
        
    print(f"Custom dictionary mapping created in {output_json} with {len(custom_map)} keys.")

if __name__ == "__main__":
    create_filtered_dictionary("dictionary_data.csv")
