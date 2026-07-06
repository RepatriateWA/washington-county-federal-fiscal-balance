import re


def normalize(text):
    if text is None:
        return ""

    text = str(text).lower()
    text = text.replace("\n", " ")
    text = re.sub(r"\[\d+\]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def find_single_value_column(df, label_text, header_row=3):
    target = normalize(label_text)

    for col in range(df.shape[1]):
        header = normalize(df.iloc[header_row, col])

        if header == target or header.startswith(target + " "):
            return col

    raise ValueError(f"Could not find column for: {label_text}")


def find_amount_column(df, label_text, header_row=3, subheader_row=4):
    target = normalize(label_text)

    for col in range(df.shape[1]):
        header = normalize(df.iloc[header_row, col])

        if target in header:
            for offset in range(0, 4):
                candidate_col = col + offset

                if candidate_col >= df.shape[1]:
                    continue

                subheader = normalize(df.iloc[subheader_row, candidate_col])

                if subheader == "amount":
                    return candidate_col

    raise ValueError(f"Could not find Amount column for: {label_text}")